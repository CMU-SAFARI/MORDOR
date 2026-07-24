#include <vector>
#include <unordered_map>
#include <limits>
#include <random>
#include <deque>

#include "base/base.h"
#include "base/type.h"
#include "dram_controller/controller.h"
#include "dram_controller/plugin.h"

namespace Ramulator {

class GrapheneDDR5 : public IControllerPlugin, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IControllerPlugin, GrapheneDDR5, "GrapheneDDR5", "Graphene with DRFM.")

  private:
    std::deque<Request> m_memory_buffer;  

    IDRAM* m_dram = nullptr;

    int m_clk = -1;

    int m_num_table_entries = -1;
    int m_activation_threshold = -1;
    int m_reset_period_ns = -1;
    int m_reset_period_clk = -1;
    bool m_is_debug = false;

    int m_DRFM_req_id = -1;

    int m_rank_level = -1;
    int m_bank_level = -1;
    int m_row_level = -1;
    int m_bank_group_level = -1; 

    int m_num_ranks = -1;
    int m_num_banks_per_rank = -1;
    int m_num_rows_per_bank = -1;

    // stats regarding the PROs issued
    int s_num_sent_drfm = 0;
    int s_num_resent_drfm = 0;
    int s_num_rejected_drfm = 0;
    int s_num_rejected_resent_drfm = 0;

    std::string m_queue_type = "priority";
    bool m_insecure_read_queue = false;

    // per bank activation count table
    // indexed using flattened <rank id, bank id>
    // e.g., if rank 0, bank 4, index is 4
    // if rank 1, bank 5, index is 16 (assuming 16 banks/rank) + 5
    std::vector<std::unordered_map<int, int>> m_activation_count_table;
    // spillover counter per bank
    std::vector<int> m_spillover_counter;


  public:
    void init() override { 
      m_num_table_entries = param<int>("num_table_entries").required();
      m_activation_threshold = param<int>("activation_threshold").required();
      m_reset_period_ns = param<int>("reset_period_ns").required();
      m_is_debug = param<bool>("debug").default_val(false);

      m_queue_type = param<std::string>("queue_type").default_val("priority"); 
      m_insecure_read_queue = param<bool>("insecure_read_queue")
                                  .desc("Send read-queue DRFMs without blacklisting their target rows.")
                                  .default_val(false);
      
      register_stat(s_num_sent_drfm).name("num_sent_DRFM");
      register_stat(s_num_resent_drfm).name("num_re-sent_DRFM");
      register_stat(s_num_rejected_drfm).name("num_rejected_DRFM");
      register_stat(s_num_rejected_resent_drfm).name("num_rejected_re-sent_DRFM");
    
    };

    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
      std::cout << "[Blacklisting]" << std::endl;
      m_ctrl = cast_parent<IDRAMController>();
      m_dram = m_ctrl->m_dram;

      if (!m_dram->m_commands.contains("DRFMsb")) {
        throw ConfigurationError("Graphene is not compatible with the DRAM implementation that does not have DRFMsb command!");
      }

      m_reset_period_clk = m_reset_period_ns / ((float) m_dram->m_timing_vals("tCK_ps") / 1000.0f);

      m_DRFM_req_id = m_dram->m_requests("same-bank-directed-rfm");

      m_rank_level = m_dram->m_levels("rank");
      m_bank_level = m_dram->m_levels("bank");
      m_row_level = m_dram->m_levels("row");
      m_bank_group_level = m_dram->m_levels("bankgroup");
   

      m_num_ranks = m_dram->get_level_size("rank");
      m_num_banks_per_rank = m_dram->get_level_size("bankgroup") == -1 ? 
                             m_dram->get_level_size("bank") : 
                             m_dram->get_level_size("bankgroup") * m_dram->get_level_size("bank");
      m_num_rows_per_bank = m_dram->get_level_size("row");

      // Initialize bank act count tables
      for (int i = 0; i < m_num_banks_per_rank * m_num_ranks; i++) {
        std::unordered_map<int, int> table;
        for (int j = -m_num_rows_per_bank; j < -m_num_rows_per_bank + m_num_table_entries; j++) {
          table.insert(std::make_pair(j, 0));
        }
        m_activation_count_table.push_back(table);
      }

      // Initialize spillover counter
      m_spillover_counter = std::vector<int>(m_num_banks_per_rank * m_num_ranks, 0);
    };

    void update(bool request_found, ReqBuffer::iterator& req_it) override {
      // Tick myself
      m_clk++;

      if (m_clk % m_reset_period_clk == 0) {
        // Reset
        for (int i = 0; i < m_num_banks_per_rank * m_num_ranks; i++) {
          for (auto it = m_activation_count_table[i].begin(); it != m_activation_count_table[i].end(); it++)
            it->second = 0;
          m_spillover_counter[i] = 0;
        }
      }

      //ceck if the read buffer has requests that should be scheduled
      if (!m_memory_buffer.empty()) {
        Request next = m_memory_buffer.front();
        m_memory_buffer.pop_front();
        bool accepted = false;
        if (m_queue_type == "read") {
          s_num_resent_drfm += 1;
          accepted = m_ctrl->send(next);
        } else {
          s_num_resent_drfm += 1;
          accepted = m_ctrl->priority_send(next);
        }
        // could not re-issue request 
        if (!accepted) {
          s_num_rejected_resent_drfm += 1;
          //std::cout << "rejected re-issued DRFM request" << std::endl;
          // prepend the rejected request to preserve FIFO order
          m_memory_buffer.push_front(next);
        }
      } else if (request_found) {
        if (m_dram->m_command_meta(req_it->command).is_opening && m_dram->m_command_scopes(req_it->command) == m_row_level) {
          int flat_bank_id = req_it->addr_vec[m_bank_level];
          int accumulated_dimension = 1;
          for (int i = m_bank_level - 1; i >= m_rank_level; i--) {
            accumulated_dimension *= m_dram->m_organization.count[i + 1];
            flat_bank_id += req_it->addr_vec[i] * accumulated_dimension;
          }
          
          int row_id = req_it->addr_vec[m_row_level];

          if (m_is_debug) {
            std::cout << "Graphene: ACT on row " << row_id << std::endl;
            std::cout << "  └  " << "rank: " << req_it->addr_vec[m_rank_level] << std::endl;
            std::cout << "  └  " << "bank_group: " << req_it->addr_vec[m_rank_level + 1] << std::endl;
            std::cout << "  └  " << "bank: " << req_it->addr_vec[m_bank_level] << std::endl;
            std::cout << "  └  " << "index: " << flat_bank_id << std::endl;
          }

          if (m_activation_count_table[flat_bank_id].find(row_id) == m_activation_count_table[flat_bank_id].end()) {
            // if row is not in the table, find an entry 
            // with a count equal to that of the spillover counter
            bool found = false;
            int to_remove = -1;
            int spillover_value = -1;

            for (auto it = m_activation_count_table[flat_bank_id].begin(); it != m_activation_count_table[flat_bank_id].end(); it++) {
              if (m_is_debug)
                std::cout << "  └  " << "checking row " << it->first << " with count " << it->second << std::endl;

              if (it->second == m_spillover_counter[flat_bank_id]) {
                // if we find an entry, record it
                spillover_value = it->second;
                to_remove = it->first;
                found = true;
                break;
              }
            }
            if (found) {
              if (m_is_debug) {
                // print the row that is being removed
                std::cout << "Removing row " << to_remove << " from table " << flat_bank_id << std::endl;
                // print the row that is being added
                std::cout << "Adding row " << row_id << " to table " << flat_bank_id << std::endl;
                std::cout << "  └  " << "spillover counter: " << m_spillover_counter[flat_bank_id] << std::endl;
              }
              // remove to_remove from the table
              m_activation_count_table[flat_bank_id].erase(to_remove);
              // add row_id to the table
              m_activation_count_table[flat_bank_id][row_id] = spillover_value + 1;
            }
            // if we did not find such an entry, increment spillover counter by one
            else {
              m_spillover_counter[flat_bank_id] += 1;
            }
          }
          else {
            // if row in table, increment its activation count
            m_activation_count_table[flat_bank_id][row_id] += 1;
            
            if (m_is_debug) {
              std::cout << "Row " << row_id << " in table[" << flat_bank_id << "]" << std::endl;
              std::cout << "  └  " << "threshold: " << m_activation_threshold << std::endl;
              std::cout << "  └  " << "count: " << m_activation_count_table[flat_bank_id][row_id] << std::endl;
            }

            // check if the count exceeds the threshold
            if (m_activation_count_table[flat_bank_id][row_id] >= m_activation_threshold) { 
              if (m_is_debug) {
                std::cout << "Row " << row_id << " in table " << flat_bank_id << " has exceeded the threshold!" << std::endl;
              }
              // if yes, schedule preventive refreshes
              Request drfm_req(req_it->addr_vec, m_DRFM_req_id);
              drfm_req.addr_vec[m_bank_group_level] = -1;

              if (m_queue_type == "read") {
                s_num_sent_drfm += 1;
                if (!m_insecure_read_queue) {
                  m_ctrl->addToBlacklist(drfm_req, false);
                }

                bool accepted = m_ctrl->send(drfm_req);
                if (!accepted) { 
                  s_num_rejected_drfm += 1;
                  m_memory_buffer.push_back(drfm_req);
                }
              } else {
                s_num_sent_drfm += 1;
                bool accepted = m_ctrl->priority_send(drfm_req);
                if (!accepted) {
                  s_num_rejected_drfm += 1;
                  m_memory_buffer.push_back(drfm_req);
                }
              }
              m_activation_count_table[flat_bank_id][row_id] = m_spillover_counter[flat_bank_id];
            }
          }
        }
      }
    }
};

}       // namespace Ramulator
