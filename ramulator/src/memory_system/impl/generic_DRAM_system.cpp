#include "memory_system/memory_system.h"
#include "translation/translation.h"
#include "dram_controller/controller.h"
#include "addr_mapper/addr_mapper.h"
#include "dram/dram.h"
using namespace std;
namespace Ramulator {
class GenericDRAMSystem final : public IMemorySystem, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IMemorySystem, GenericDRAMSystem, "GenericDRAM", "A generic DRAM-based memory system.");
  protected:
    Clk_t m_clk = 0;
    IDRAM*  m_dram;
    IAddrMapper*  m_addr_mapper;
    std::vector<IDRAMController*> m_controllers;
  public:
    int s_num_read_requests = 0;
    int s_num_write_requests = 0;
    int s_num_other_requests = 0;
    int s_num_DRFM_refreshes = 0; 
    int s_num_DRFMab_refreshes = 0; 
    int s_num_RFM_refreshes = 0;

  public:
    void init() override { 
      // Create device (a top-level node wrapping all channel nodes)
      m_dram = create_child_ifce<IDRAM>();
      std::cout << "m_addr_mapper = create_child_ifce<IAddrMapper>();" << std::endl;
      m_addr_mapper = create_child_ifce<IAddrMapper>();
      int num_channels = m_dram->get_level_size("channel");   
      // Create memory controllers
      for (int i = 0; i < num_channels; i++) {
        IDRAMController* controller = create_child_ifce<IDRAMController>();
        controller->m_impl->set_id(fmt::format("Channel {}", i));
        controller->m_channel_id = i;
        m_controllers.push_back(controller);
      }
      m_clock_ratio = param<uint>("clock_ratio").required();
      register_stat(m_clk).name("memory_system_cycles");
      register_stat(s_num_read_requests).name("total_num_read_requests");
      register_stat(s_num_write_requests).name("total_num_write_requests");
      register_stat(s_num_other_requests).name("total_num_other_requests");
      register_stat(s_num_DRFM_refreshes).name("total_num_DRFM_requests");
      register_stat(s_num_DRFMab_refreshes).name("total_num_DRFMab_requests");
      register_stat(s_num_RFM_refreshes).name("total_num_RFMab_requests");
    };
    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override { }
    bool inc_req_count(Request& req) override {
        int m_DRFM_req_id = m_dram->m_requests("same-bank-directed-rfm");
        switch (req.type_id) {
          case Request::Type::Read: {
            s_num_read_requests++;
            break;
          }
          case Request::Type::Write: {
            s_num_write_requests++;
            break;
          }
          case Request::Type::DRFMsb: {
            s_num_DRFM_refreshes++;
            break;
          }
          default: {
            if (req.type_id == m_dram->m_requests("directed-rfm")) {
              s_num_DRFMab_refreshes++; 
            } else if (req.type_id == m_dram->m_requests("rfm")) {
              s_num_RFM_refreshes++;
            } else s_num_other_requests++;
            //std::cerr << "incremented req count for: " << req.type_id << std::endl; 
            break;
          }
        }
        return true; 
    }
    bool send(Request req) override {
      //std::cout << "Received request of type: " << req.type_id << " for address: " << std::hex << req.addr << std::dec << std::endl;
      m_addr_mapper->apply(req);
      int channel_id = req.addr_vec[0];
      bool is_success = m_controllers[channel_id]->send(req);
      return is_success;
    };
  
    void tick() override {
      m_clk++;
      m_dram->tick();
      for (auto controller : m_controllers) {
        controller->tick();
      }
      /*
      if (m_clk % 10000 == 0) {
        std::cout << "issued" << s_num_DRFM_refreshes << " so far" << std::endl;
      }
      */
    };
    float get_tCK() override {
      return m_dram->m_timing_vals("tCK_ps") / 1000.0f;
    }
    // const SpecDef& get_supported_requests() override {
    //   return m_dram->m_requests;
    // };
};
  
}   // namespace 

