#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <queue>
#include <sstream>
#include <string>
#include <vector>

#include "base/base.h"
#include "base/type.h"
#include "dram_controller/controller.h"
#include "dram_controller/plugin.h"

namespace Ramulator {

class DAPPER_DDR5 : public IControllerPlugin, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IControllerPlugin, DAPPER_DDR5, "DAPPER_DDR5", "DAPPER with DRFM.")

    private: 
    int m_clk = -1;
    int m_reset_period_clk;
    
    size_t row_group_size = 256;
    std::string m_queue_type = "priority"; 
    bool m_insecure_read_queue = false;
    bool m_is_debug = false;
    int m_rowhammer_treshold;
    int m_mitigation_threshold;

    int m_bank_level;
    int m_rank_level;
    int m_bank_group_level;
    int m_row_level;
    int m_num_ranks;
    int m_num_banks_per_rank;
    int m_num_rows_per_bank;
    size_t m_num_group_counters;
    int m_num_total_rows;

    int s_issue_DRFM_to = -1;

    int m_DRFM_req_id;

    IDRAM *m_dram = nullptr;

    int s_num_sent_drfm = 0;
    int s_num_resent_drfm = 0;
    int s_num_rejected_drfm = 0;
    int s_num_rejected_resent_drfm = 0;

    struct SeededHash {
        size_t seed = 0;
        size_t min = 0;
        size_t max = 0;

        size_t operator()(size_t key) const {
            uint64_t z = splitmix64(key + splitmix64(seed));
            return min + (z % (max - min + 1));
        }
    };

    // alternatively, use 2 seeded hash functions that produce outputs
    // in the desired range
    SeededHash hash1;
    SeededHash hash2;

    std::vector<int> row_group_counter_1;
    std::vector<int> row_group_counter_2;

    int m_reset_counter1;
    int m_reset_counter2;

    // bit vector: m_num_group_counters x n_num_banks
    int m_bit_vector_size;
    std::vector<std::vector<int>> m_bit_vector;

    // keep track of which address vectors map to which counters
    std::vector<std::vector<AddrVec_t>> m_rgc_mappings_1;
    std::vector<std::vector<AddrVec_t>> m_rgc_mappings_2;

    // queue for requests rejected by the memory controller
    std::queue<Request> m_memory_buffer;

    // returned ranged seeded hash function
    static uint64_t splitmix64(uint64_t x) {
        x += 0x9e3779b97f4a7c15ULL;
        x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
        x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
        return x ^ (x >> 31);
    }

    SeededHash make_seeded_hash(size_t seed, size_t min, size_t max) {
        return SeededHash{seed, min, max};
    }

    void init() override {
        m_is_debug = param<bool>("debug").default_val(false);
        m_queue_type = param<std::string>("queue_type").default_val("priority"); 
        m_insecure_read_queue = param<bool>("insecure_read_queue")
                                    .desc("Send read-queue DRFMs without blacklisting their target rows.")
                                    .default_val(false);
        m_rowhammer_treshold = param<int>("tRH").required();
    };

    void setup(IFrontEnd *frontend, IMemorySystem *memory_system) override {
        m_ctrl = cast_parent<IDRAMController>();
        m_dram = m_ctrl->m_dram;
        if (!m_dram->m_commands.contains("DRFMsb")) {
        throw ConfigurationError(
          "DAPPER is not compatible with the DRAM implementation that does not "
          "have DRFMsb command!");
        }

        int m_reset_period_ns = 64000000;  // tREFW = 64ms (section iv, simulation framework, page 6)
        m_reset_period_clk =
        m_reset_period_ns / ((float)m_dram->m_timing_vals("tCK_ps") / 1000.0f);

        size_t reset_cycles_32ms = 32000000 / ((float)m_dram->m_timing_vals("tCK_ps") / 1000.0f);
        size_t ns2 = 2/((float)m_dram->m_timing_vals("tCK_ps") / 1000.0f);
        std::cout << "[32ms is " << reset_cycles_32ms << " cycles, 2ns are " << ns2 << " clock cycles]" << std::endl;

        m_mitigation_threshold = m_rowhammer_treshold/2;

        m_num_ranks = m_dram->get_level_size("rank");
        m_num_banks_per_rank = m_dram->get_level_size("bankgroup") == -1
                               ? m_dram->get_level_size("bank")
                               : m_dram->get_level_size("bankgroup") *
                                     m_dram->get_level_size("bank");
        m_num_rows_per_bank = m_dram->get_level_size("row");
        m_row_level = m_dram->m_levels("row");
        m_bank_level = m_dram->m_levels("bank");
        m_bank_group_level = m_dram->m_levels("bankgroup");
        m_rank_level = m_dram->m_levels("rank");
        
        m_num_total_rows = m_num_ranks * m_num_banks_per_rank * m_num_rows_per_bank;
        m_num_group_counters = m_num_total_rows / row_group_size;

        // initialize seeded hash functions
        hash1 = make_seeded_hash(69, 0, m_num_group_counters-1);
        hash2 = make_seeded_hash(13452942, 0, m_num_group_counters-1);

        // group counters, index with row group ID [0, m_num_group_counters)
        row_group_counter_1 = std::vector<int>(m_num_group_counters, 0);
        row_group_counter_2 = std::vector<int>(m_num_group_counters, 0);

        m_rgc_mappings_1.resize(m_num_group_counters);
        m_rgc_mappings_2.resize(m_num_group_counters);

        m_reset_counter1 = 0;
        m_reset_counter2 = 0;

        // create bit vectors for all row groups in table 1
        m_bit_vector_size = m_num_banks_per_rank * m_num_ranks;
        std::cout << "[we have " << m_num_banks_per_rank << " banks per rank and " << m_num_ranks << " ranks]" << std::endl;
        m_bit_vector = std::vector<std::vector<int>>(m_num_group_counters, std::vector<int>(m_bit_vector_size, 0));

        m_DRFM_req_id = m_dram->m_requests("same-bank-directed-rfm");

        register_stat(m_num_group_counters).name("num_group_counters");
        register_stat(m_bit_vector_size).name("bit_vector_size");
        register_stat(m_reset_period_clk).name("reset_period_clk");

        register_stat(s_num_sent_drfm).name("num_sent_DRFM");
        register_stat(s_num_resent_drfm).name("num_re-sent_DRFM");
        register_stat(s_num_rejected_drfm).name("num_rejected_DRFM");
        register_stat(s_num_rejected_resent_drfm).name("num_rejected_re-sent_DRFM");

        print_stats();
    };

    // Utitlity functions for debugging and verification
    std::string get_string_addr(const AddrVec_t& addr) {
        std::ostringstream a; 
        for (size_t i=0; i<addr.size(); ++i) {
            a << addr[i];
        }
        return a.str();
    };

    void print_stats() {
        std::cout << "[Group Counters: " << m_num_group_counters << "]" << std::endl;
        std::cout << "[Total Rows: " << m_num_total_rows << "]" << std::endl;
        std::cout << "[Total Banks, aka Bit-Vector Size: " << m_bit_vector_size << "]" << std::endl;
        std::cout << "[Reset Period (Clock Cycles): " << m_reset_period_clk << "]" << std::endl;
    };

//#define DEBUG
  #ifdef DEBUG
    #define HERE std::cout << "[HERE] " << __FILE__ << ":" << __FUNCTION__ << ":" << __LINE__ << std::endl
    #define DEBUG_PRINT(x) std::cout << x << std::endl
  #else
    #define DEBUG_PRINT(x)
    #define HERE
  #endif 

    
// helper functions for base actions

    void clear_bit_for_other_banks(size_t group_counter, int dont_clear) {
        auto& bits = m_bit_vector[group_counter];
        if (dont_clear < 0) {
            std::fill(bits.begin(), bits.end(), 0);
            return;
        }

        int keep = bits[dont_clear];
        std::fill(bits.begin(), bits.end(), 0);
        bits[dont_clear] = keep;
    };

    void clear_counter_table(std::vector<int>& counters) {
        std::fill(counters.begin(), counters.end(), 0);
    }

    void clear_bit_vectors() {
        for (auto& bits : m_bit_vector) {
            std::fill(bits.begin(), bits.end(), 0);
        }
    };

    void clear_rgc_mappings() {
        for (auto& bucket : m_rgc_mappings_1) {
            bucket.clear();
        }
        for (auto& bucket : m_rgc_mappings_2) {
            bucket.clear();
        }
    }

    void clear_everything() {
        // clear bit vector
        clear_bit_vectors();

        // clear group-counter table entries
        clear_counter_table(row_group_counter_1);
        clear_counter_table(row_group_counter_2);

        // clear simulator-side membership for the current reset window
        clear_rgc_mappings();

        m_reset_counter1 = 0;
        m_reset_counter2 = 0;
    };

    void reissue_request() {
        Request& next = m_memory_buffer.front(); 
        bool accepted = false;
        if (m_queue_type == "priority" && next.type_id == m_DRFM_req_id) {
          DEBUG_PRINT("re-issueing a priority DRFM");
          accepted = m_ctrl->priority_send(next);
        } else {
          DEBUG_PRINT("re-issueing a read-queue DRFM");
          accepted = m_ctrl->send(next); 
        }
        if (accepted) {
            m_memory_buffer.pop();
            s_num_resent_drfm += 1;
        }
        else s_num_rejected_resent_drfm += 1;
    };

    size_t get_row_addr(const AddrVec_t& vec) {
        std::string res_str;
        res_str.reserve(32);

        // only use channel, rank, bankgroup, bank, and row values
        for(int i=0; i<5; i++) {
            res_str += std::to_string(vec[i]);
        }

        return std::stoll(res_str);
    }


    std::vector<AddrVec_t> get_common_elements(size_t index_1, size_t index_2) {
        DEBUG_PRINT("rgc 1 has " << m_rgc_mappings_1[index_1].size() << " entries, rgc 2 has "
            << m_rgc_mappings_2[index_2].size() << " entries");
        std::vector<AddrVec_t> result;
        const auto& vec1 = m_rgc_mappings_1[index_1];
        const auto& vec2 = m_rgc_mappings_2[index_2];
        result.reserve(std::min(vec1.size(), vec2.size()));

        for (const AddrVec_t& entry1 : vec1) {
            for (const AddrVec_t& entry2 : vec2) {
                if (entry1 == entry2) {
                    result.push_back(entry1);
                    break;
                }
            }
        }
        return result;
    }

    void issue_preventive_refresh(const AddrVec_t& addr_vec) {
        Request drfm_req(addr_vec, m_DRFM_req_id);
        drfm_req.addr_vec[m_bank_group_level] = -1; 

        if (m_queue_type == "read") {
            DEBUG_PRINT("issueing a read-queue DRFM");
            if (!m_insecure_read_queue) {
                m_ctrl->addToBlacklist(drfm_req, false);
            }
            bool accepted = m_ctrl->send(drfm_req); 
            if (!accepted) {
                m_memory_buffer.push(drfm_req);
                s_num_rejected_drfm += 1;
            }
        } else {
            DEBUG_PRINT("issueing a priority DRFM");
            bool accepted = m_ctrl->priority_send(drfm_req);
            if (!accepted) {
                m_memory_buffer.push(drfm_req);
                s_num_rejected_drfm += 1;
            } 
        }
    };


    // looks up the max counter value in the other table, for any row that 
    // maps to the counter we are resetting
    // arguments: counter that overflowed in table A, mappings for table A, 
    // hash function for table B, table B, counter in table B
    int get_reset_counter(size_t counter1, const std::vector<std::vector<AddrVec_t>>& mapping,
        const SeededHash& hash, const std::vector<int>& table, size_t counter2) {
        // get all addresses mapped to counter in table A
        const auto& addrs = mapping[counter1];
        int max = 0; 
        for (const AddrVec_t& addr_vec : addrs) {
            // iterate over addresses, and get highest counter from table B
            size_t row_addr = get_row_addr(addr_vec);
            size_t other_counter = hash(row_addr);
            // we exclude the counter for the row we are mitigating
            if (other_counter != counter2 && table[other_counter] > max) {
                max = table[other_counter];
            }
        }
        DEBUG_PRINT("iterated over " << addrs.size() << " addresses, max is " << max);
        return max;
    };


    void update_reset_counters(size_t h1, size_t h2) {
        int reset1 = get_reset_counter(h1, m_rgc_mappings_1, hash2, row_group_counter_2, h2);
        int reset2 = get_reset_counter(h2, m_rgc_mappings_2, hash1, row_group_counter_1, h1);
        // increase the reset counter, if the new counter is higher than the old one
        if (m_reset_counter1 < reset1) m_reset_counter1 = reset1;
        if (m_reset_counter2 < reset2) m_reset_counter2 = reset2;
        DEBUG_PRINT("counter values: c1=" << m_reset_counter1 << ", c2=" << m_reset_counter2);
    }

    void issue_mitigation(size_t h1, size_t h2) {
        // issue DRFM requests to all elements that appear in both group counter tables
        // only refresh rows shared between the two RGCs
        std::vector<AddrVec_t> commons = get_common_elements(h1, h2);

        DEBUG_PRINT("sending DRFMs to " << commons.size() << " rows");
        int num_drfms = commons.size();
        if (s_issue_DRFM_to < num_drfms)
            s_issue_DRFM_to = num_drfms;
        s_num_sent_drfm += num_drfms;
        for(const auto& addr : commons) {
            issue_preventive_refresh(addr);
        }

        update_reset_counters(h1, h2);
        row_group_counter_1[h1] = m_reset_counter1;
        row_group_counter_2[h2] = m_reset_counter2;

        // reset the entire bit vector
        clear_bit_for_other_banks(h1, -1);
    };


    bool compare(const AddrVec_t& v1, const AddrVec_t& v2) {
        // only compare channel, rank, bankgroup, bank and row bits (not column bits)
        for (int i=0; i<5; i++) {
            if (v1[i] != v2[i]) return false;
        }
        return true;
    }

    // adds a new mapping for address vector to hash value
    // the point of this is to make issueing DRFMs easier later
    void add_rgc_mapping(std::vector<std::vector<AddrVec_t>>& mapping, size_t hash_value, const AddrVec_t& addr_vec) {
        auto& bucket = mapping[hash_value];
        bool exists = std::any_of(bucket.begin(), bucket.end(), [&](const AddrVec_t& existing) {
            return compare(existing, addr_vec); });
        
        if (!exists) {
            bucket.push_back(addr_vec);
        }
    };


    

    public:
    virtual void update(bool request_found, ReqBuffer::iterator& req_it) override {
        m_clk++;
        if (m_clk % m_reset_period_clk == 0) {
            // reset RGC tables and bit vectors
            clear_everything();
            DEBUG_PRINT("cleared all values, reset counters");
        }

        if (!m_memory_buffer.empty()) {
            reissue_request();
        } else if (request_found) {
            if (
                m_dram->m_command_meta(req_it->command).is_opening && 
                m_dram->m_command_scopes(req_it->command) == m_row_level
            ) {
                DEBUG_PRINT("row address is " << req_it->addr_vec[m_row_level]);

                // use custom row-addresses (everything except for the column bits)
                size_t addr = get_row_addr(req_it->addr_vec);
                DEBUG_PRINT("full row address is " << addr);
                size_t h1 = hash1(addr);
                size_t h2 = hash2(addr);


                // keep the address vectors to issue DRFMs later
                add_rgc_mapping(m_rgc_mappings_1, h1, req_it->addr_vec);
                add_rgc_mapping(m_rgc_mappings_2, h2, req_it->addr_vec);

                // check if bit vector is set
                int bit_vector_index = req_it->addr_vec[m_rank_level] + req_it->addr_vec[m_bank_level] 
                    + req_it->addr_vec[m_bank_group_level];
                DEBUG_PRINT("row addr is " << addr << ", addr is " << req_it->addr << ", request addr_vec is " << get_string_addr(req_it->addr_vec) << 
                    ", counters " << h1 << " and " << h2 << ", bit vecor index: " << bit_vector_index);
                if (m_bit_vector[h1][bit_vector_index] == 0) {
                    // if not, set bit vector, only increment the row-group counter in table 2
                    m_bit_vector[h1][bit_vector_index] = 1;
                    row_group_counter_2[h2] ++;
                    DEBUG_PRINT("bit vector is 0");
                } else {
                    // update both row-group counters
                    DEBUG_PRINT("bit vector is 1, incrementing both counters");
                    row_group_counter_1[h1] ++;
                    row_group_counter_2[h2] ++;

                    // clear the bit for other banks
                    clear_bit_for_other_banks(h1, bit_vector_index);

                    if (row_group_counter_1[h1] >= m_mitigation_threshold &&
                        row_group_counter_2[h2] >= m_mitigation_threshold) {
                        // both counters have reached the mitigation threshold -> issue preventive refresh
                        DEBUG_PRINT("exceeded threshold " << m_mitigation_threshold << 
                            " for counters " << h1 << " and " << h2);
                        issue_mitigation(h1, h2);
                    }
                }

            }
        }
    };
};

}       // namespace Ramulator
