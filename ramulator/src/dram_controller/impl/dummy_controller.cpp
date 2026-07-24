#include "dram_controller/controller.h"

namespace Ramulator {

class DummyController final : public IDRAMController, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IDRAMController, DummyController, "DummyController", "A dummy memory controller.");

  public:
    void init() override {
      return;
    };

    bool send(Request& req) override {
      if (req.callback) {
        req.callback(req);
      }
      return true; 
    };

    bool priority_send(Request& req) override {
      if (req.callback) {
        req.callback(req);
      }
      return true; 
    };

    void tick() override {
      return;
    }
  
    bool is_to_open_row(ReqBuffer::iterator req) override {
      for (auto it = m_active_buffer.begin(); it != m_active_buffer.end(); ++it) {
        if (it == req)
          return true;
      }
      return false;
    }

    void addToBlacklist(Request& req, bool ab) override {}
    bool checkBlacklisted(AddrVec_t& address) override {return false;}
    void increment_proq_waits(AddrVec_t addr_vec) override {}
    int get_proq_waits(AddrVec_t addr_vec) override {
      return -1;
    }
  };

}   // namespace Ramulator