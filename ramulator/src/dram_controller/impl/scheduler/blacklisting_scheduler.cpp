#include <iostream>
#include <vector>

#include "base/base.h"
#include "base/request.h"
#include "base/type.h"
#include "dram_controller/controller.h"
#include "dram_controller/scheduler.h"

namespace Ramulator {

class FRFCFS_blacklisting : public IScheduler, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(
      IScheduler, FRFCFS_blacklisting, "FRFCFS_blacklisting",
      "FRFCFS DRAM Scheduler with Aggressor Row Blacklisting.")
private:
  Clk_t m_clk = 0;
  IDRAM *m_dram;
  IDRAMController *m_controller;
  std::vector<AddrVec_t> m_blacklist;

  float s_num_qos_inc = 0;

public:
  void init() override {};

  void setup(IFrontEnd *frontend, IMemorySystem *memory_system) override {
    m_dram = cast_parent<IDRAMController>()->m_dram;
    m_controller = cast_parent<IDRAMController>();
    m_blacklist = m_controller->blacklist;
    register_stat(s_num_qos_inc).name("number_of_qos_counters_incremented");
  };


  ReqBuffer::iterator compare_old(ReqBuffer::iterator req1, ReqBuffer::iterator req2) {
    bool ready1 = m_dram->check_ready(req1->command, req1->addr_vec);
      bool ready2 = m_dram->check_ready(req2->command, req2->addr_vec);

      if (ready1 ^ ready2) {
        if (ready1) {
          return req1;
        } else {
          return req2;
        }
      }

      // Fallback to FCFS
      if (req1->arrive <= req2->arrive) {
        return req1;
      } else {
        return req2;
      } 
  }

  ReqBuffer::iterator compare(ReqBuffer::iterator req1,
                              ReqBuffer::iterator req2) override {
    bool ready1 = m_dram->check_ready(req1->command, req1->addr_vec);
    bool ready2 = m_dram->check_ready(req2->command, req2->addr_vec);

    bool b1 = m_controller->checkBlacklisted(req1->addr_vec);
    bool b2 = m_controller->checkBlacklisted(req2->addr_vec);

    bool blacklisted1 = (b1 && (req1->type_id != m_dram->m_requests("same-bank-directed-rfm"))
        && (req1->type_id!=m_dram->m_requests("directed-rfm"))) && !is_to_open_row(req1)
        && (req1->type_id!=m_dram->m_requests("all-bank-refresh"));
    bool blacklisted2 = b2 && (req2->type_id != m_dram->m_requests("same-bank-directed-rfm")
        && (req2->type_id!=m_dram->m_requests("directed-rfm"))) && !is_to_open_row(req2)
        && (req2->type_id!=m_dram->m_requests("all-bank-refresh"));

    // return the request that is ready and not blacklisted
    bool rnb1 = ready1 && !blacklisted1;
    bool rnb2 = ready2 && !blacklisted2;


    // only one is ready & not blacklisted
    if (rnb1 ^ rnb2) {
      if (rnb1) return req1;
      else return req2;
    }

    // Fallback to FCFS
    if (req1->arrive <= req2->arrive) {
      return req1;
    } else {
      return req2;
    }
  }

  bool is_to_open_row(ReqBuffer::iterator req) {
    return m_controller->is_to_open_row(req);
  }

  ReqBuffer::iterator get_best_request(ReqBuffer &buffer) override {
    if (buffer.size() == 0) {
      return buffer.end();
    }

    for (auto &req : buffer) {
      req.command = m_dram->get_preq_command(req.final_command, req.addr_vec);
    }

    auto candidate = buffer.begin();
    for (auto next = std::next(buffer.begin(), 1); next != buffer.end();
         next++) {
      candidate = compare(candidate, next);
    }

    return candidate;
  }

  ReqBuffer::iterator get_best_request_old(ReqBuffer &buffer) override {
    if (buffer.size() == 0) {
        return buffer.end();
      }

      for (auto& req : buffer) {
        req.command = m_dram->get_preq_command(req.final_command, req.addr_vec);
      }

      auto candidate = buffer.begin();
      for (auto next = std::next(buffer.begin(), 1); next != buffer.end(); next++) {
        candidate = compare_old(candidate, next);
      }
      return candidate;
  }

      
  virtual void tick() override {
        m_clk++;
  }

};

} // namespace Ramulator
