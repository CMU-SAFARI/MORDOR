#include "base/base.h"
#include "base/type.h"
#include "frontend/frontend.h"
#include "translation/translation.h"
#include "addr_mapper/addr_mapper.h"
#include "dram_controller/controller.h"
#include "dram_controller/plugin.h"
#include "memory_system/memory_system.h"
#include <cstddef>
#include <ostream>

namespace Ramulator {
    class AbacusDDR5 : public IControllerPlugin, public Implementation {
    RAMULATOR_REGISTER_IMPLEMENTATION(IControllerPlugin, AbacusDDR5, "AbacusDDR5", "ABACus with DRFM")
    

    private:
        std::queue<Request> m_memory_buffer;
        IDRAM* m_dram = nullptr;
        ITranslation* m_translation = nullptr;
        IAddrMapper* m_addr_mapper = nullptr;
        IMemorySystem* m_system = nullptr;

        int m_clk = -1;

        std::string m_queue_type = "priority"; 
        bool m_insecure_read_queue = false;
        std::string m_rcc_policy = "RANDOM";

        //int m_DRFM_req_id = -1;
        int m_DRFMab_req_id = -1;

        int m_rank_level = -1;
        int m_bank_group_level = -1;
        int m_bank_level = -1;
        int m_row_level = -1;
        int m_col_level = -1;

        int m_num_ranks = -1;
        int m_num_banks_per_rank = -1;
        int m_num_rows_per_bank = -1;
        int m_num_banks = -1;

        bool m_is_debug;

        int m_REF_ab_req_id = -1; 

        // ABACuS paremeters:
        int m_refresh_cycle_threshold = -1;
        int m_preventive_refresh_threshold = -1; 
        size_t m_refresh_window = -1; 
        size_t m_abacus_reset_window = -1;
        size_t m_spillover_counter = -1;
    
        int m_s_rac = -1;      // size of row activation counter
        int m_s_sav = -1;      // size of sibling activation vector
        int m_n_entries = -1;  // number of counters in counter table

        // timing parameters to compute N_entries
        float m_t_rfc = -1; 
        float m_t_refi = -1; 
        float m_trc = -1; 

        float m_n_rfc = -1; 
        float m_n_refi = -1; 
        float m_nrc = -1; 

        // ABACuS datastructures:
        struct m_ABACuS_Counter {
            std::vector<bool> m_sav;  // sibling activation vector
            int m_rac;                // row activation counter
        };
        std::unordered_map <int, m_ABACuS_Counter> m_ABACuS_Counter_Table; 

        struct count_entry {
            int rac;        // Row Activation Counter
            uint64_t sav;   // Sibling Activation Vector
        };

        std::unordered_map<int, struct count_entry> abacus_counter;

    public: 

//#define DEBUG
  #ifdef DEBUG
    #define HERE std::cout << "[HERE] " << __FILE__ << ":" << __FUNCTION__ << ":" << __LINE__ << std::endl
    #define DEBUG_PRINT(x) std::cout << x << std::endl
  #else
    #define DEBUG_PRINT(x)
    #define HERE
  #endif 

#define RDEBUG
  #ifdef RDEBUG
    #define RDEBUG_PRINT(x) std::cout << x << std::endl
  #else
    #define RDEBUG_PRINT(x)
  #endif 

    void init() override {
        m_is_debug = param<bool>("debug").default_val(false);
        m_preventive_refresh_threshold = param<int>("preventive_refresh_threshold").required();
        m_refresh_cycle_threshold = param<int>("refresh_cycle_threshold").required(); 
        m_queue_type = param<std::string>("queue_type").default_val("priority");
        m_insecure_read_queue = param<bool>("insecure_read_queue")
                                    .desc("Send read-queue DRFMs without blacklisting their target rows.")
                                    .default_val(false);
        m_refresh_window = 32000000;
        m_abacus_reset_window = 32000000;
        m_clk = 0;
    };

    void setup (IFrontEnd* frontend, IMemorySystem* memory_system) override {
        m_ctrl = cast_parent<IDRAMController>();
        m_dram = m_ctrl->m_dram;

        m_translation = frontend->get_ifce<ITranslation>();
        m_addr_mapper = memory_system->get_ifce<IAddrMapper>();

        if (!m_dram->m_commands.contains("DRFMsb")) {
            throw ConfigurationError("ABACuSDDR5 is not compatible with the DDR5 implementation that does not have DRFMsb!");
        }

        m_rank_level = m_dram->m_levels("rank");
        m_bank_level = m_dram->m_levels("bank");
        m_bank_group_level = m_dram->m_levels("bankgroup");
        m_row_level = m_dram->m_levels("row");

        m_num_ranks = m_dram->get_level_size("rank");
        m_num_rows_per_bank = m_dram->get_level_size("row");
        m_num_banks_per_rank = m_dram->get_level_size("bankgroup") == -1
                               ? m_dram->get_level_size("bank")
                               : m_dram->get_level_size("bankgroup") *
                                     m_dram->get_level_size("bank");

        m_DRFMab_req_id = m_dram->m_requests("directed-rfm");
        m_REF_ab_req_id = m_dram->m_requests("all-bank-refresh");

        m_n_rfc = m_dram->m_timing_vals("nRFC1");
        m_n_refi = m_dram->m_timing_vals("nREFI"); 
        m_nrc = m_dram->m_timing_vals("nRC");

        float tCK_ps = 1E6 / (m_dram->m_timing_vals("rate") / 2.0);
        float tCK_ns = tCK_ps / 1000;

        m_t_rfc = m_n_rfc * tCK_ns;
        m_t_refi = m_n_refi * tCK_ns;
        m_trc = m_nrc * tCK_ns;

        DEBUG_PRINT("tRFC: " << m_t_rfc << ", tREFI:" << m_t_refi << ", tRC:" << m_trc);



        // ABACuS Counter Table
        size_t m_n_entries = (m_refresh_window * (1-m_t_rfc/m_t_refi) / m_trc) 
            / m_preventive_refresh_threshold; 
        std::cout << "[we have " << m_num_rows_per_bank << " rows per bank & thus this many table entries]" << std::endl;
        // all row IDs are negative, for every row the RAC=0 and SAV is vector of false values
        m_num_banks = m_num_banks_per_rank * m_num_ranks;
        DEBUG_PRINT("we have " << m_num_banks << " Banks, and thus this many SAV entries, and " << m_num_banks_per_rank << " banks per rank");
        for (int i=0; i<m_num_rows_per_bank; i++) {
            m_ABACuS_Counter_Table.insert(std::make_pair(i, m_ABACuS_Counter {std::vector<bool>(m_num_banks, false), 0}));
        }

        m_spillover_counter = 0;
    }

    void reset_everything() {
        m_ABACuS_Counter_Table.clear(); 
        m_num_banks = m_num_banks_per_rank * m_num_ranks;
        for (int i=0; i<m_num_rows_per_bank; i++) {
            m_ABACuS_Counter_Table.insert(std::make_pair(i, m_ABACuS_Counter {std::vector<bool>(m_num_banks, false), 0})); 
        }
        m_spillover_counter = 0; 
    };

    void add_all_banks_to_blacklist(Request drfm_req) {
        if (m_insecure_read_queue) {
            return;
        }

        for (int i=0; i<32; i++) {
            drfm_req.addr_vec[m_bank_level] = i;
            m_ctrl->addToBlacklist(drfm_req, true);
        }
    };

    void send_DRFM(AddrVec_t addr_vec) {
        Request drfm_req(addr_vec, m_DRFMab_req_id);
        drfm_req.addr_vec[m_bank_group_level] = -1;
        drfm_req.addr_vec[m_bank_level] = -1;
        if (m_queue_type == "read") {
            add_all_banks_to_blacklist(drfm_req);
            bool accepted = m_ctrl->send(drfm_req);
            if (!accepted) m_memory_buffer.push(drfm_req);
        } else {
            bool accepted = m_ctrl->priority_send(drfm_req);
            if (!accepted) m_memory_buffer.push(drfm_req);
        }
    };

    void update(bool request_found, ReqBuffer::iterator& req_it) override {
        m_clk ++; 
        if (m_clk % m_abacus_reset_window == 0) {
            DEBUG_PRINT("reached reset period");
            reset_everything();
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
            if (m_dram->m_command_meta(req_it->command).is_opening && m_dram->m_command_scopes(req_it->command) == m_row_level) {
            
                int flat_bank_id = req_it->addr_vec[m_bank_level];
                int accumulated_dimension = 1;
                for (int i = m_bank_level - 1; i >= m_rank_level; i--) {
                    accumulated_dimension *= m_dram->m_organization.count[i + 1];
                    flat_bank_id += req_it->addr_vec[i] * accumulated_dimension;
                }
                size_t row_id = req_it->addr_vec[m_row_level];
                DEBUG_PRINT("checking row id " << row_id << ", bank id " << flat_bank_id);
                auto it = m_ABACuS_Counter_Table.find(row_id);
                if (it != m_ABACuS_Counter_Table.end()) {
                    DEBUG_PRINT("row " << row_id << " is already tracked by an ABACuS Counter");

                    if (it->second.m_sav[flat_bank_id]) {
                        it->second.m_rac += 1;
                        std::fill(it->second.m_sav.begin(), it->second.m_sav.end(), false);

                        it->second.m_sav[flat_bank_id] = true;
                        DEBUG_PRINT("sav bit set for row " << row_id << " incremented counter to " << it->second.m_rac);

                        if (it->second.m_rac >= m_preventive_refresh_threshold) {
                            DEBUG_PRINT("reached threshold " << m_preventive_refresh_threshold << " sending DRFM!");
                            send_DRFM(req_it->addr_vec);
                            m_ABACuS_Counter_Table.erase(it);
                            m_ABACuS_Counter_Table.insert(std::make_pair(row_id, m_ABACuS_Counter {std::vector<bool>(m_num_banks, false), 0}));
                        }
                    } else {
                        DEBUG_PRINT("sav bit not set for row " << row_id << ", setting it");
                        it->second.m_sav[flat_bank_id] = true;
                    }

                } else {
                    std::cout << "this should not happen" << std::endl;
                    DEBUG_PRINT("row " << row_id << " is not yet tracked by an ABACuS counter, spillover counter is " << m_spillover_counter);
                    bool found_RAC = false;
                    for (auto it2 = m_ABACuS_Counter_Table.begin(); it2 != m_ABACuS_Counter_Table.end(); ) {
                        if (it2->second.m_rac == m_spillover_counter) {
                            DEBUG_PRINT("found counter with value " << m_spillover_counter << ", currently tracking row " << it2->first);
                            found_RAC = true;

                            m_ABACuS_Counter counter = it2->second;
                            if (flat_bank_id >= it2->second.m_sav.size()) {
                                std::cout << "249: out of bounds access to m_sav entry " << flat_bank_id << ", sav size is " << it2->second.m_sav.size()  << std::endl;
                            }
                            m_ABACuS_Counter_Table.erase(it2);
                            counter.m_rac += 1;

                            counter.m_sav[flat_bank_id] = 1;
                            m_ABACuS_Counter_Table.insert({row_id, counter});
                            break;
                        }
                        ++ it2;
                    }
                    DEBUG_PRINT("exit loop");
                    
                    if (!found_RAC) {
                        m_spillover_counter += 1;
                        DEBUG_PRINT("unable to track row, incrementing spillover counter to " << m_spillover_counter);
                        if (m_spillover_counter >= m_preventive_refresh_threshold) {
                            RDEBUG_PRINT("[all bank refresh]");
                            RDEBUG_PRINT("row_id: " << row_id << ", spillover counter: " << m_spillover_counter << ", threshold: " << m_preventive_refresh_threshold);
                            Request all_bank_refresh_req (req_it->addr_vec, m_REF_ab_req_id);
                            all_bank_refresh_req.addr_vec[m_bank_group_level] = -1;
                            all_bank_refresh_req.addr_vec[m_bank_level] = -1;
                            m_ctrl->priority_send(all_bank_refresh_req);
                            reset_everything();
                            RDEBUG_PRINT("spillover counter: " << m_spillover_counter);
                        }
                    }
                }

            }
        }
    };
};
}
