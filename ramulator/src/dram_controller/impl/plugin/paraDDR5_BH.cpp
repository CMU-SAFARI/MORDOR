#include <vector>
#include <unordered_map>
#include <limits>
#include <random>

#include "base/base.h"
#include "dram_controller/controller.h"
#include "dram_controller/plugin.h"

namespace Ramulator {

class PARAddr5 : public IControllerPlugin, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IControllerPlugin, PARAddr5, "PARAddr5_BH", "PARA with DRFM for BH.")

  private:
    std::queue<Request> m_memory_buffer;  

    IDRAM* m_dram = nullptr;

    float m_pr_threshold;

    int   m_seed;
    std::mt19937 m_generator;
    std::uniform_real_distribution<float> m_distribution;
    bool m_is_debug = false;

    int m_DRFM_req_id = -1;
    int m_bank_level = -1;
    int m_row_level = -1;
    int m_bank_group_level = -1; 

    int s_num_drfm = 0;

    std::string m_queue_type = "priority"; 

  public:
    void init() override { 
      m_pr_threshold = param<float>("threshold").desc("Probability threshold for issuing neighbor row refresh").required();
      if (m_pr_threshold <= 0.0f || m_pr_threshold >= 1.0f)
        throw ConfigurationError("Invalid probability threshold ({}) for PARA!", m_pr_threshold);

      m_seed = param<int>("seed").desc("Seed for the RNG").default_val(123);
      m_generator = std::mt19937(m_seed);
      m_distribution = std::uniform_real_distribution<float>(0.0, 1.0);

      m_is_debug = param<bool>("debug").default_val(false);

      m_queue_type = param<std::string>("queue_type").default_val("priority"); 
    };

    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
      m_ctrl = cast_parent<IDRAMController>();
      m_dram = m_ctrl->m_dram;

      if (!m_dram->m_commands.contains("DRFMsb")) {
        throw ConfigurationError("PARA is not compatible with the DRAM implementation that does not have DRFM command!");
      }

      m_DRFM_req_id = m_dram->m_requests("same-bank-directed-rfm");
      m_bank_level = m_dram->m_levels("bank");
      m_row_level = m_dram->m_levels("row");
      m_bank_group_level = m_dram->m_levels("bankgroup");

      register_stat(s_num_drfm).name("paraddr5_num_drfm");
    };

    void update(bool request_found, ReqBuffer::iterator& req_it) override {
      if (request_found) {
        if (
            m_dram->m_command_meta(req_it->command).is_opening && 
            m_dram->m_command_scopes(req_it->command) == m_row_level
        ) {
            if (m_distribution(m_generator) < m_pr_threshold) {
                Request drfm_req(req_it->addr_vec, m_DRFM_req_id);
                drfm_req.addr_vec[m_bank_group_level] = -1;
                m_ctrl->priority_send(drfm_req);
                s_num_drfm++;
            }
        }
      }
    };

};

}       // namespace Ramulator
