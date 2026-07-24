#ifndef RAMULATOR_IDEAL_QPRAC_H
#define RAMULATOR_IDEAL_QPRAC_H

#include <cstdint>

#include "base/base.h"
#include "base/request.h"

namespace Ramulator {

class IIdealQPRAC {
public:
  virtual ~IIdealQPRAC() = default;

  /*
   * Return the currently hottest row according to the ideal QPRAC tracker.
   *
   * Returns false if no row has been activated yet or all tracked counts are 0.
   */
  virtual bool get_hot_row(AddrVec_t& addr_vec, uint64_t& count) = 0;

  /*
   * Reset the activation count for a row after a DRFM services it.
   */
  virtual void reset_count(const AddrVec_t& addr_vec) = 0;
};

}  // namespace Ramulator

#endif  // RAMULATOR_IDEAL_QPRAC_H