#include <vector>
#include <deque>
#include <unordered_map>
#include <limits>
#include <random>
#include <iostream>
using namespace std;

// type to store agressor and victims as a triple
using TripleType = std::tuple<std::vector<int>, vector<int>, vector<int>>;

#include "base/base.h"
#include "dram_controller/controller.h"
#include "dram_controller/plugin.h"
#include "memory_system/memory_system.h"

namespace Ramulator {

class OracleRHelastic : public IControllerPlugin, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IControllerPlugin, OracleRHelastic, "OracleRHelastic", "Oracle RowHammer defense with Elastic refresh")

  private:
    IDRAM* m_dram = nullptr;

    // set of triples (agressor addr, victim 1 addr, victim2 addr) if only one victim, other is set to -1
    std::set<TripleType> agr_v_v;

    // added for send call: 
    IMemorySystem* m_system = nullptr; 

    using BankACTCounter = std::unordered_map<Addr_t, int>;
    std::vector<BankACTCounter> m_table;
    std::vector<int> m_rank_REF_counter;

    int m_RH_threshold = -1;

    int m_VRR_req_id = -1;

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

    void update(bool request_found, ReqBuffer::iterator& req_it) override {
      if (request_found) {
        if (req_it->type_id == Request::Type::Read) {
          AddrVec_t read_addr = req_it->addr_vec; 
          for (const auto& triple : agr_v_v) {
            if ((std::get<1>(triple) == read_addr && std::get<2>(triple)[m_row_level] == -1) || (std::get<2>(triple) == read_addr && std::get<1>(triple)[m_row_level] == -1)) {  
                AddrVec_t agrVec = std::get<0>(triple);

                // get agressor m_table values to reset tRH
                int flat_bank_id = agrVec[m_bank_level];
                int accumulated_dimension = 1;
                for (int i = m_bank_level - 1; i >= m_rank_level; i--) {
                  accumulated_dimension *= m_dram->m_organization.count[i + 1];
                  flat_bank_id += agrVec[i] * accumulated_dimension;
                }
                int row_id = agrVec[m_row_level];

                //cout << "got read to victim " << read_addr[m_row_level] << " & reset tRH counter at tRH value = " << m_table[flat_bank_id][row_id] << "\n";
                agr_v_v.erase(triple);  
                m_table[flat_bank_id][row_id] = 0; 

                break; 
            } else if (std::get<1>(triple) == read_addr) {
                AddrVec_t seen_victim_read = read_addr; 
                seen_victim_read[m_row_level] = -1; 
                agr_v_v.insert(std::make_tuple(std::get<0>(triple), seen_victim_read, std::get<2>(triple)));
                agr_v_v.erase(triple); 
                //cout << "got read to vicim at " <<  read_addr[m_row_level] << "\n";
                break; 
            } else if (std::get<2>(triple) == read_addr) {
                AddrVec_t seen_victim_read = read_addr; 
                seen_victim_read[m_row_level] = -1; 
                agr_v_v.insert(std::make_tuple(std::get<0>(triple), std::get<1>(triple), seen_victim_read));
                agr_v_v.erase(triple); 
                //cout << "got read to vicim at " <<  read_addr[m_row_level] << "\n";
                break; 
            }
          }
        }
        if (
          m_dram->m_command_meta(req_it->command).is_opening && 
          m_dram->m_command_scopes(req_it->command) == m_row_level
        ) {
          int flat_bank_id = req_it->addr_vec[m_bank_level];
          int accumulated_dimension = 1;
          // TODO: add this computation to other table indexing
          for (int i = m_bank_level - 1; i >= m_rank_level; i--) {
            accumulated_dimension *= m_dram->m_organization.count[i + 1];
            flat_bank_id += req_it->addr_vec[i] * accumulated_dimension;
          }
          
          int row_id = req_it->addr_vec[m_row_level];
          if (m_table[flat_bank_id].find(row_id) != m_table[flat_bank_id].end()) {
            m_table[flat_bank_id][row_id]++;

            if (m_table[flat_bank_id][row_id] == m_RH_threshold) { 
              //cout << "tRH exceeded at  " << row_id << " with tRH=" << m_table[flat_bank_id][row_id] << "\n";
              // send the elastic refresh as a read to neightbouring rows
              AddrVec_t addr1 = req_it->addr_vec;
              Addr_t agr = addr1[m_row_level];  


              AddrVec_t vec1 = addr1;
              vec1[m_row_level] = -1;
              AddrVec_t vec2 = addr1;
              vec2[m_row_level] = -1;
              
              if (agr < m_num_rows_per_bank) {
                Addr_t v1 = agr + 1; 
                vec1[m_row_level] = v1; 
                Request read1(vec1, Request::Type::Read);
                //bool accepted = m_ctrl->send_preventative_read_refresh(read1); 
                bool accepted = m_ctrl->priority_send(read1);
                if (!accepted) {
                  accepted = m_ctrl->priority_send(read1); 
                  if (!accepted) throw ConfigurationError("ERROR: preventive read rejected by memory controller from priority queue"); 
                }
                //cout << "issued read to " << v1 << " " << accepted << "\n";
              } 

              if (agr > 0) {
                Addr_t v2 = agr -1; 
                vec2[m_row_level] = v2; 
                Request read2(vec2, Request::Type::Read);
                //bool accepted = m_ctrl->send_preventative_read_refresh(read2); 
                bool accepted = m_ctrl->priority_send(read2); 
                if (!accepted) {
                  accepted = m_ctrl->priority_send(read2); 
                  if (!accepted) throw ConfigurationError("ERROR: preventive read rejected by memory controller from priority queue"); 
                }
                //cout << "issued read to " << v2 << " " << accepted << "\n";
              } 

              // keep track of aggressor and victims in triple: 
              agr_v_v.insert(std::make_tuple(addr1, vec1, vec2)); 
              //cout << "added to map victims " << v1 << " " << v2 << "\n"; 
            }
          } else {  
            m_table[flat_bank_id][row_id] = 1;
          }
        } else if (
          m_dram->m_command_meta(req_it->command).is_refreshing && 
          m_dram->m_command_scopes(req_it->command) == m_rank_level) {

            int rank_id = req_it->addr_vec[m_rank_level];

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
