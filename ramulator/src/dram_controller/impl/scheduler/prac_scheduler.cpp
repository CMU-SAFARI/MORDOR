#include <iostream>
#include <vector>
#include <unordered_map>

#include "base/base.h"
#include "base/request.h"
#include "base/type.h"
#include "dram_controller/controller.h"
#include "dram_controller/scheduler.h"
#include "dram_controller/impl/plugin/prac.h"

namespace Ramulator {

class FRFCFS_PRAC : public IScheduler, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(
      IScheduler, FRFCFS_PRAC, "FRFCFS_PRAC",
      "PRAC-style scheduler without blacklisting.");

private:

  IDRAM* m_dram = nullptr;
  IDRAMController* m_controller = nullptr;
  IPRAC* m_prac = nullptr;

  std::unordered_map<int, int> lut_cycles_needed;

  Clk_t m_clk = 0;
  bool m_is_debug = false;

  const int FITS_IDX = 0;
  const int READY_IDX = 1;

public:
  void init() override {
    m_is_debug = param<bool>("debug").default_val(false);
  }

  void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
    m_controller = cast_parent<IDRAMController>();
    m_dram = m_controller->m_dram;

    m_prac = m_controller->get_plugin<IPRAC>();
    if (!m_prac) {
      std::cout << "[RAMULATOR::PRACSched] Need PRAC plugin!" << std::endl;
      std::exit(0);
    }
  }

  bool is_rfm(const Request& req) const {
    return (req.type_id == m_dram->m_requests("same-bank-directed-rfm")) ||
           (req.type_id == m_dram->m_requests("directed-rfm"));
  }

  bool is_urgent_rfm(const Request& req) const {
    if (!is_rfm(req)) {
      return false;
    }

    // If it no longer fits before the next recovery point, treat it as urgent.
    return !req.scratchpad[FITS_IDX];
  }

  ReqBuffer::iterator compare(ReqBuffer::iterator req1,
                              ReqBuffer::iterator req2) override {
    bool rfm1 = is_rfm(*req1);
    bool rfm2 = is_rfm(*req2);

    if (rfm1 ^ rfm2) {
      return rfm1 ? req1 : req2;
    }

    bool fits1 = req1->scratchpad[FITS_IDX];
    bool fits2 = req2->scratchpad[FITS_IDX];

    if (fits1 ^ fits2) {
      return fits1 ? req1 : req2;
    }

    bool ready1 = req1->scratchpad[READY_IDX];
    bool ready2 = req2->scratchpad[READY_IDX];

    if (ready1 ^ ready2) {
      return ready1 ? req1 : req2;
    }

    // Fallback to FCFS
    return (req1->arrive <= req2->arrive) ? req1 : req2;
  }

  ReqBuffer::iterator get_best_request(ReqBuffer& buffer) override {
    if (buffer.size() == 0) {
      return buffer.end();
    }

    Clk_t next_recovery = m_prac->next_recovery_cycle();

    for (auto& req : buffer) {
      req.command = m_dram->get_preq_command(req.final_command, req.addr_vec);

      req.scratchpad[FITS_IDX] =
          (m_clk + m_prac->min_cycles_with_preall(req) < next_recovery);

      req.scratchpad[READY_IDX] =
          m_dram->check_ready(req.command, req.addr_vec);

      if (m_is_debug) {
        std::cout << "[PRACSched] clk=" << m_clk
                  << " type=" << req.type_id
                  << " cmd=" << req.command
                  << " final_cmd=" << req.final_command
                  << " arrive=" << req.arrive
                  << " fits=" << req.scratchpad[FITS_IDX]
                  << " ready=" << req.scratchpad[READY_IDX]
                  << " is_rfm=" << is_rfm(req)
                  << " urgent_rfm=" << is_urgent_rfm(req)
                  << std::endl;
      }
    }

    auto candidate = buffer.begin();
    for (auto next = std::next(buffer.begin()); next != buffer.end(); ++next) {
      candidate = compare(candidate, next);
    }

    if (m_is_debug && candidate != buffer.end()) {
      std::cout << "[PRACSched] SELECT clk=" << m_clk
                << " type=" << candidate->type_id
                << " cmd=" << candidate->command
                << " final_cmd=" << candidate->final_command
                << " arrive=" << candidate->arrive
                << " fits=" << candidate->scratchpad[FITS_IDX]
                << " ready=" << candidate->scratchpad[READY_IDX]
                << " is_rfm=" << is_rfm(*candidate)
                << " urgent_rfm=" << is_urgent_rfm(*candidate)
                << std::endl;
    }

    return candidate;
  }


  void tick() override {
    m_clk++;
  }
 
  ReqBuffer::iterator get_best_request_old(ReqBuffer& buffer) override {
    return get_best_request(buffer);
  }
};

} // namespace Ramulator