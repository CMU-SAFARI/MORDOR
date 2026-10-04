#include <limits>
#include <ostream>
#include <random>
#include <semaphore>
#include <unordered_map>
#include <vector>

#include "base/base.h"
#include "dram_controller/controller.h"
#include "dram_controller/plugin.h"

namespace Ramulator {

class COMET : public IControllerPlugin, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IControllerPlugin, COMET, "COMET", "COMET")
private:
  IDRAM *m_dram = nullptr;
  std::string m_queue_type = "priority";
  bool m_insecure_read_queue = false;

  std::queue<Request> m_memory_buffer;

  int m_clk = -1;

  int m_num_table_entries = -1;
  int m_activation_threshold = -1;
  int m_reset_period_ns = -1;
  int m_reset_period_clk = -1;
  bool m_is_debug = false;

  int m_DRFM_req_id = -1;
  int m_REF_ab_req_id = -1;

  int m_rank_level = -1;
  int m_bank_level = -1;
  int m_row_level = -1;
  int m_bank_group_level = -1;

  int m_num_ranks = -1;
  int m_num_banks_per_rank = -1;
  int m_num_rows_per_bank = -1;
  int m_num_bankgroups = -1;
  int m_num_banks = -1;

  int no_counters_per_hash = 512;
  int no_hashes = 4;

  bool debug = false;
  bool debug_verbose = false;
  bool debug_misuse = false;
  bool conservative = false;
  bool misuse_refresh = true;

  std::vector<std::deque<bool>> misuse_bits; // per bank misuse bits
  int misuse_history_length = 256;           // ACTs
  float misuse_threshold = 0.5;

  // per bank activation count table
  // indexed using flattened <rank id, bank id>
  // e.g., if rank 0, bank 4, index is 4
  // if rank 1, bank 5, index is 16 (assuming 16 banks/rank) + 5
  // spillover counter per bank

  std::vector<std::vector<std::unordered_map<int, int>>> activation_count_table;
  std::vector<std::unordered_map<int, int>> aggressor_cache;
  int cache_size = 128;

  typedef std::function<uint16_t(uint16_t)> HashFunction;
  std::unordered_map<int, HashFunction> hashFunctions;

  std::unordered_map<int, HashFunction> getHashFunctions(uint16_t m,
                                                         uint16_t k) {
    std::unordered_map<int, HashFunction> hashFunctions;
    std::mt19937 gen(100); // Use a fixed seed value for deterministic results
    std::uniform_int_distribution<uint16_t> shiftDist(0, 15);
    std::set<uint16_t> shifts;
    for (uint16_t i = 0; i < k; ++i) {
      uint16_t shift = shiftDist(gen);
      while ((k < 16) && shifts.find(shift) != shifts.end()) {
        shift = shiftDist(gen);
      }
      shifts.insert(shift);
      hashFunctions[i] = [shift, m](uint16_t address) -> uint16_t {
        return ((address << shift) | (address >> (16 - shift))) % m;
      };
    }
    if (debug) {
      // print the contents of the hashFunctions
      for (const auto &hashFunction : hashFunctions) {
        std::cout << "Hash function: " << hashFunction.first << " ";
        std::cout << "Hash: " << hashFunction.second(123) << std::endl;
      }
    }
    return hashFunctions;
  }

public:
  void init() override {
    std::cout << "[latest comet build 2.2]" << std::endl;

    no_counters_per_hash = param<int>("no_counters_per_hash").required();
    no_hashes = param<int>("no_hashes").required();
    cache_size = param<int>("rat_size").required();
    m_activation_threshold =
        param<int>("activation_threshold").required(); // this is tRH
    // CoMeT selects k=3, so its reset period is tREFW/k. Our DDR5
    // configuration uses a 32 ms refresh window.
    m_reset_period_ns =
        param<int>("reset_period_ns").default_val(10666667);
    m_is_debug = param<bool>("debug").default_val(false);
    m_queue_type = param<std::string>("queue_type").default_val("priority");
    m_insecure_read_queue = param<bool>("insecure_read_queue")
                                .desc("Send read-queue DRFMs without blacklisting their target rows.")
                                .default_val(false);
  };

  void setup(IFrontEnd *frontend, IMemorySystem *memory_system) override {
    m_ctrl = cast_parent<IDRAMController>();
    m_dram = m_ctrl->m_dram;

    if (!m_dram->m_commands.contains("DRFMsb")) {
      throw ConfigurationError(
          "COMET is not compatible with the DRAM implementation that does not "
          "have DRFMsb command!");
    }

    m_reset_period_clk =
        m_reset_period_ns / ((float)m_dram->m_timing_vals("tCK_ps") / 1000.0f);
    register_stat(m_reset_period_clk).name("reset_period_clk");

    m_DRFM_req_id = m_dram->m_requests("same-bank-directed-rfm");
    m_REF_ab_req_id = m_dram->m_requests("all-bank-refresh");

    m_rank_level = m_dram->m_levels("rank");
    m_bank_level = m_dram->m_levels("bank");
    m_row_level = m_dram->m_levels("row");
    m_bank_group_level = m_dram->m_levels("bankgroup");

    m_num_ranks = m_dram->get_level_size("rank");
    m_num_banks_per_rank = m_dram->get_level_size("bankgroup") == -1
                               ? m_dram->get_level_size("bank")
                               : m_dram->get_level_size("bankgroup") *
                                     m_dram->get_level_size("bank");
    m_num_rows_per_bank = m_dram->get_level_size("row");
    m_num_bankgroups = m_dram->get_level_size("bankgroup");
    m_num_banks = m_dram->get_level_size("bank");

    // Initialize bank act count tables
    for (int i = 0; i < m_num_banks * m_num_bankgroups * m_num_ranks; i++) {
      std::vector<std::unordered_map<int, int>> table;
      for (int j = 0; j < no_hashes; j++) {
        std::unordered_map<int, int> table_per_hash;
        for (int k = 0; k < no_counters_per_hash; k++)
          table_per_hash.insert(std::make_pair(k, 0));
        table.push_back(table_per_hash);
      }
      activation_count_table.push_back(table);

      std::unordered_map<int, int> cache;
      for (int j = -1; j > -1 - cache_size; j--)
        cache.insert(std::make_pair(j, 0));
      aggressor_cache.push_back(cache);

      std::deque<bool> misuse_bit;
      for (int j = 0; j < misuse_history_length; j++)
        misuse_bit.push_back(false);
      misuse_bits.push_back(misuse_bit);
    }
    hashFunctions = getHashFunctions(no_counters_per_hash, no_hashes);
  };

  void update(bool request_found, ReqBuffer::iterator &req_it) override {

    // Tick myself
    m_clk++;

    if (m_clk % m_reset_period_clk == 0) {
      // Reset
      //
      for (int i = 0; i < m_num_banks * m_num_bankgroups * m_num_ranks; i++) {
        for (int j = 0; j < no_hashes; j++) {
          for (int k = 0; k < no_counters_per_hash; k++) {
            auto counter = activation_count_table[i][j].find(k);
            counter->second = 0;
          }
        }

        aggressor_cache[i].clear();
        for (int j = -1; j > -1 - cache_size; j--)
          aggressor_cache[i].insert(std::make_pair(j, 0));

        for (int j = 0; j < misuse_history_length; j++) {
          misuse_bits[i][j] = false;
        }
      }
    }

    if (!m_memory_buffer.empty()) {
      Request next = m_memory_buffer.front();
      bool accepted = false;
      if (m_queue_type == "read") {
        accepted = m_ctrl->send(next);
      } else {
        accepted = m_ctrl->priority_send(next);
      }
      if (accepted) {
        m_memory_buffer.pop();
      }
    } else if (request_found) {
      if (m_dram->m_command_meta(req_it->command).is_opening &&
          m_dram->m_command_scopes(req_it->command) == m_row_level) {

        int flat_bank_id = req_it->addr_vec[m_bank_level];
        int accumulated_dimension = 1;
        for (int i = m_bank_level - 1; i >= m_rank_level; i--) {
          accumulated_dimension *= m_dram->m_organization.count[i + 1];
          flat_bank_id += req_it->addr_vec[i] * accumulated_dimension;
        }

        int row_id = req_it->addr_vec[m_row_level];

        if (m_is_debug) {
          std::cout << "CMS: ACT on row " << row_id << std::endl;
        }

        int rank_id = req_it->addr_vec[m_rank_level];
        int bankgroup_id = req_it->addr_vec[m_bank_group_level];
        int bank_id = req_it->addr_vec[m_bank_level];

        int index = rank_id * m_num_banks * m_num_bankgroups +
                    bankgroup_id * m_num_banks + bank_id;
        // check the RAT
        auto cache_entry = aggressor_cache[index].find(row_id);
        if (cache_entry != aggressor_cache[index].end()) {
          // fount entry in RAT
          cache_entry->second += 1;

          // if cache entry is greater than threshold, schedule preventive
          // refreshes
          if (cache_entry->second >= m_activation_threshold) {
            // if yes, schedule preventive refreshes
            if (m_is_debug) {
              std::cout << "Row " << row_id << " in table " << flat_bank_id
                        << " has exceeded the threshold!" << std::endl;
            }
            // if yes, schedule preventive refreshes
            Request drfm_req(req_it->addr_vec, m_DRFM_req_id);
            drfm_req.addr_vec[m_bank_group_level] = -1;

            if (m_queue_type == "read") {
              // blacklist the address until DRFM request complete
              if (!m_insecure_read_queue) {
                m_ctrl->addToBlacklist(drfm_req, false);
              }
              bool accepted = m_ctrl->send(drfm_req);
              if (!accepted)
                m_memory_buffer.push(drfm_req);
            } else {
              bool accepted = m_ctrl->priority_send(drfm_req);
              if (!accepted)
                m_memory_buffer.push(drfm_req);
            }
            // reset counter here
            cache_entry->second = 0;
          }

          int index = rank_id * m_num_banks * m_num_bankgroups +
                      bankgroup_id * m_num_banks + bank_id;
          misuse_bits[index].pop_front();
          misuse_bits[index].push_back(false);
          return;
        }

        // row is not in the aggressor cache (RAT)
        // check rows counters (CT)
        int min_ctr = INT_MAX;
        std::vector<int> indices;
        // check the counter values to determine whether to send preventive
        // refreshes
        for (int i = 0; i < no_hashes; i++) {
          int index = rank_id * m_num_banks * m_num_bankgroups +
                      bankgroup_id * m_num_banks + bank_id;
          int hash = hashFunctions[i](row_id);
          indices.push_back(hash);
          auto counter = activation_count_table[index][i].find(hash);
          int counter_value = counter->second;
          if (min_ctr > counter_value)
            min_ctr = counter_value;
        }

        // if min counter is already equal to or greater than the threshold push
        // true to misuse bit
        if (min_ctr >= m_activation_threshold) {
          // increase misuse bit
          int index = rank_id * m_num_banks * m_num_bankgroups +
                      bankgroup_id * m_num_banks + bank_id;
          misuse_bits[index].pop_front();
          misuse_bits[index].push_back(true);
        }
        // update counters
        for (int i = 0; i < no_hashes; i++) {
          int index = rank_id * m_num_banks * m_num_bankgroups +
                      bankgroup_id * m_num_banks + bank_id;
          int hash = indices[i];
          auto counter = activation_count_table[index][i].find(hash);
          // update the counter value
          // conservative mode: only update if the counter value == the min_ctr
          if (counter->second >= m_activation_threshold)
            continue;
          if (conservative) {
            if (counter->second == min_ctr)
              counter->second += 1;
          } else
            counter->second += 1;
        }

        int updated_min_ctr = min_ctr + 1;

        if (misuse_refresh) {
          int rank_id = req_it->addr_vec[m_rank_level];
          int bankgroup_id = req_it->addr_vec[m_bank_group_level];
          int bank_id = req_it->addr_vec[m_bank_level];
          int index = rank_id * m_num_banks * m_num_bankgroups +
                      bankgroup_id * m_num_banks + bank_id;
          std::deque<bool> misuse = misuse_bits[index];
          int misused = 0;
          for (int i = 0; i < misuse_history_length; i++) {
            if (misuse[i]) {
              misused++;
            }
          }
          double misused_ratio =
              (double)misused / (double)misuse_history_length;
          if (misused_ratio > misuse_threshold) {
            // refresh the complete dram rank
            Request all_bank_refresh_req(req_it->addr_vec, m_REF_ab_req_id);
            all_bank_refresh_req.addr_vec[m_bank_group_level] = -1;
            all_bank_refresh_req.addr_vec[m_bank_level] = -1;
            m_ctrl->priority_send(all_bank_refresh_req);
            // clear enerything
            for (int i = 0; i < m_num_banks * m_num_bankgroups * m_num_ranks;
                 i++) {
              for (int j = 0; j < no_hashes; j++) {
                for (int k = 0; k < no_counters_per_hash; k++) {
                  auto counter = activation_count_table[i][j].find(k);
                  counter->second = 0;
                }
              }

              aggressor_cache[i].clear();
              for (int j = -1; j > -1 - cache_size; j--)
                aggressor_cache[i].insert(std::make_pair(j, 0));

              for (int j = 0; j < misuse_history_length; j++) {
                misuse_bits[i][j] = false;
              }
            }
            return;
          }
        }

        if (updated_min_ctr >= m_activation_threshold) {
          // this row
          // if yes, schedule preventive refreshes
          Request drfm_req(req_it->addr_vec, m_DRFM_req_id);
          drfm_req.addr_vec[m_bank_group_level] = -1;

          if (m_queue_type == "read") {
            // blacklist the address until DRFM request complete
            if (!m_insecure_read_queue) {
              m_ctrl->addToBlacklist(drfm_req, false);
            }
            bool accepted = m_ctrl->send(drfm_req);
            if (!accepted)
              m_memory_buffer.push(drfm_req);
          } else {
            bool accepted = m_ctrl->priority_send(drfm_req);
            if (!accepted)
              m_memory_buffer.push(drfm_req);
          }

          // cannot reset counter here
          // insert in aggressor cache
          // find a free entry in the cache
          int rank_id = req_it->addr_vec[m_rank_level];
          int bankgroup_id = req_it->addr_vec[m_bank_group_level];
          int bank_id = req_it->addr_vec[m_bank_level];
          int index = rank_id * m_num_banks * m_num_bankgroups +
                      bankgroup_id * m_num_banks + bank_id;

          int remove_key = 0;
          bool found = false;
          for (auto it = aggressor_cache[index].begin();
               it != aggressor_cache[index].end(); it++) {
            if (it->first < 0) {
              // we have found an unused entry in the RAT
              found = true;
              remove_key = it->first;
              break;
            }
          }

          if (found) {
            // remove to_remove from the table
            aggressor_cache[index].erase(remove_key);
            // add row_id to the table
            aggressor_cache[index][row_id] = 0;
            if (debug) {
              std::cout << "CMS: " << "index: " << index << " row " << row_id
                        << " added to aggressor cache" << std::endl;
            }
          } else {
            // no free entry found in RAT
            // rand generator for cache indexing
            static std::mt19937 rng(
                100); // Use a fixed seed value for deterministic results
            std::uniform_int_distribution<uint16_t> indexDistribution(
                0, cache_size);
            int random_index = indexDistribution(rng) % cache_size;

            // no free entry found
            int max_count = 0;
            int max_count_key = -1;
            int i = 0;
            for (auto entry : aggressor_cache[index]) {
              if (i == random_index) {
                max_count = entry.second;
                max_count_key = entry.first;
              }
              i++;
            }

            aggressor_cache[index].erase(max_count_key);
            aggressor_cache[index][row_id] = 0;
          }
        }
      }
    }
  }
};

} // namespace Ramulator
