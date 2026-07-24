#include <vector>
#include <deque>
#include <unordered_map>
#include <limits>
#include <random>
#include <iostream>
using namespace std;

#include "base/base.h"
#include "dram_controller/controller.h"
#include "dram_controller/plugin.h"
#include "memory_system/memory_system.h"

namespace Ramulator {

class OracleRHddr5 : public IControllerPlugin, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IControllerPlugin, OracleRHddr5, "OracleRHddr5", "Oracle RowHammer defense with DRFM")

  private:
    IDRAM* m_dram = nullptr;

    // added for send call: 
    IMemorySystem* m_system = nullptr; 

    using BankACTCounter = std::unordered_map<Addr_t, int>;
    std::vector<BankACTCounter> m_table;
    std::vector<int> m_rank_REF_counter;

    int m_RH_threshold = -1;

    int m_DRFM_req_id = -1;

    int m_rank_level = -1;
    int m_bank_level = -1;
    int m_row_level = -1;

    int m_num_ranks = -1;
    int m_num_banks_per_rank = -1;
    int m_num_rows_per_bank = -1;

    bool m_is_debug = false;

  public:
    void init() override { 
      m_is_debug = param<bool>("debug").default_val(false);
      m_RH_threshold = param<int>("tRH").required();

    };

    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
      m_ctrl = cast_parent<IDRAMController>();
      m_dram = m_ctrl->m_dram;

      //added for send call 
      m_system = memory_system; 

      // use DDR5 analogon of VRR
      if (!m_dram->m_commands.contains("DRFMsb")) {
        throw ConfigurationError("OracleRH is not compatible with the DDR5 implementation that does not have DRFMsb");
      }

      m_DRFM_req_id = m_dram->m_requests("same-bank-directed-rfm");  
    
      m_rank_level = m_dram->m_levels("rank");
      m_bank_level = m_dram->m_levels("bank");
      m_row_level = m_dram->m_levels("row");

      m_num_ranks = m_dram->get_level_size("rank");
      m_num_banks_per_rank = m_dram->get_level_size("bankgroup") == -1 ? 
                             m_dram->get_level_size("bank") : 
                             m_dram->get_level_size("bankgroup") * m_dram->get_level_size("bank");
      m_num_rows_per_bank = m_dram->get_level_size("row");

      m_table.resize(m_num_banks_per_rank * m_num_ranks);
      m_rank_REF_counter.resize(m_num_ranks, 0);
    };

    // basically: if tRH is exceeted -> issue maitnance refresh request
    void update(bool request_found, ReqBuffer::iterator& req_it) override {
      if (request_found) { 
        if (
          m_dram->m_command_meta(req_it->command).is_opening && 
          m_dram->m_command_scopes(req_it->command) == m_row_level
        ) {
          int flat_bank_id = req_it->addr_vec[m_bank_level];
          int accumulated_dimension = 1;
          for (int i = m_bank_level - 1; i >= m_rank_level; i--) {
            accumulated_dimension *= m_dram->m_organization.count[i + 1];
            flat_bank_id += req_it->addr_vec[i] * accumulated_dimension;
          }
          
          int row_id = req_it->addr_vec[m_row_level];
          if (m_table[flat_bank_id].find(row_id) != m_table[flat_bank_id].end()) {
            if (req_it->type_id == m_DRFM_req_id) cout << "observed DRFM request\n";
            m_table[flat_bank_id][row_id]++;

            if (m_table[flat_bank_id][row_id] >= m_RH_threshold) { 

              // here the RH threshold is exceeded and the counter in m_table is reset 
              m_table[flat_bank_id][row_id] = 0;     
              Request drfm_req(req_it->addr_vec, m_DRFM_req_id);

              // the request is enqueued in the priority buffer of the MC
              //bool success = m_ctrl->priority_send(drfm_req);
              //if (!success) throw ConfigurationError("ERROR: preventive read rejected by memory controller"); 

              // send DRFM request to the read request queue instead 
              bool success = m_ctrl->send(drfm_req); 
              if (!success) throw ConfigurationError("ERROR: preventive read rejected by memory controller"); 
            }
          } else {  
            m_table[flat_bank_id][row_id] = 1;
          }
        } else if (
          m_dram->m_command_meta(req_it->command).is_refreshing && 
          m_dram->m_command_scopes(req_it->command) == m_rank_level) {

            int rank_id = req_it->addr_vec[m_rank_level];
            // count the reference to this bank -> why?
            m_rank_REF_counter[rank_id]++;
            if (m_rank_REF_counter[rank_id] == 8191) {
              for (int i = rank_id * m_num_banks_per_rank; i < (rank_id + 1) * m_num_banks_per_rank; i++) {
                m_table[i].clear();
              }
              m_rank_REF_counter[rank_id] = 0;
            }
        }
      }
    };

};

}       // namespace Ramulator
