#include <string>
#include <vector>

#include "base/base.h"
#include "dram_controller/controller.h"
#include "dram_controller/scheduler.h"

//#define DEBUG
#ifdef DEBUG
  #define HERE std::cerr << "[HERE] " << __FILE__ << ":" << __FUNCTION__ << ":" << __LINE__ << std::endl
  #define DEBUG_PRINT(x) std::cerr << "SC: " << x << std::endl
#else
  #define DEBUG_PRINT(x)
  #define HERE
#endif 


/*
* Sourced from Ramulator.
* FRFCFS_PriorHit - First Ready First Come First Serve Prioritize Hits
* This scheduling policy behaves the same way as FRFCFS, except that it
* prioritizes row hits more than readiness. 
*/
namespace Ramulator {

class FRFCFS_prior_hit : public IScheduler, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IScheduler, FRFCFS_prior_hit, "FRFCFS_prior_hit", "FRFCFS scheduler with prioritized row hits.")
  private:
    IDRAM* m_dram;
    IDRAMController* m_controller;

    // function to get the string representation of an address vector
    std::string get_string_addr(AddrVec_t addr) {
      std::ostringstream a; 
      for (size_t i=0; i<addr.size(); ++i) {
        a << addr[i];
      }
      return a.str();
    }

  public:
    void init() override { };

    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
      m_dram = cast_parent<IDRAMController>()->m_dram;
      m_controller = cast_parent<IDRAMController>();
      int scope = m_dram->m_command_scopes("PRE");
      DEBUG_PRINT("PRE scope: " << scope);
    };

    // get address prefix of rows that are affected by a PRE command
    std::vector<int> get_pre_rowgroup(const std::vector<int>& addr_vec) {
      HERE;
      int scope = m_dram->m_command_scopes("PRE");
      HERE;
      return std::vector<int>(addr_vec.begin(), addr_vec.begin() + scope + 1);
    }

    // DRFMab addresses have -1 as wildcards for banks, so we need to check for that when comparing rowgroups
    static inline bool has_wildcard(const std::vector<int>& addr_vec) {
      for (int x : addr_vec) if (x < 0) return true;
      return false;
    }


    ReqBuffer::iterator compare(ReqBuffer::iterator req1, ReqBuffer::iterator req2) override {
      bool row_hit1 = false;
      bool row_hit2 = false;
      if (!has_wildcard(req1->addr_vec)) {
        row_hit1 =m_dram->check_rowbuffer_hit(req1->command, req1->addr_vec);
      }
      if (!has_wildcard(req2->addr_vec)) {
        row_hit2 = m_dram->check_rowbuffer_hit(req2->command, req2->addr_vec);
      }

      bool ready1 = m_dram->check_ready(req1->command, req1->addr_vec) && row_hit1;
      bool ready2 = m_dram->check_ready(req2->command, req2->addr_vec) && row_hit2;


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

    // copy of FRFCFS compare
    ReqBuffer::iterator compare_frfcfs(ReqBuffer::iterator req1, ReqBuffer::iterator req2) {
      HERE;
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
      HERE;
    }

    ReqBuffer::iterator get_best_request(ReqBuffer& buffer) override {
      HERE;
      if (buffer.size() == 0) {
        return buffer.end();
      }
      HERE;
      for (auto& req : buffer) {
        req.command = m_dram->get_preq_command(req.final_command, req.addr_vec);
      }
      HERE;
      auto candidate = buffer.begin();
      for (auto next = std::next(buffer.begin(), 1); next != buffer.end(); next++) {
        
        candidate = compare(candidate, next);
      }
      HERE;
      // if best candidate is a row hit and ready, return it
      {
        HERE;
        DEBUG_PRINT("candidate: " << get_string_addr(candidate->addr_vec));
        bool row_hit = false;
        if (!has_wildcard(candidate->addr_vec)) {
          // not DRFMsb request, so we can check for row hit
          row_hit = m_dram->check_rowbuffer_hit(candidate->command, candidate->addr_vec);
        }
        HERE;
        bool ready = m_dram->check_ready(candidate->command, candidate->addr_vec);
        HERE;
        if (row_hit && ready) {
          HERE;
          DEBUG_PRINT("got row hit and ready request to " << get_string_addr(candidate->addr_vec));
          return candidate;
        }
      }
      HERE;
      // if not, we want to preserve potential row hits -> issue requests accordingly
      DEBUG_PRINT("no row hit and ready request -> constructing hit rowgroups");
      std::vector <std::vector<int>> hit_rowgroups;
      hit_rowgroups.reserve(buffer.size());
      for (auto it = buffer.begin(); it != buffer.end(); ++it) {
        bool row_hit = false;
        if (!has_wildcard(it->addr_vec)) {
          row_hit = m_dram->check_rowbuffer_hit(it->command, it->addr_vec);
        }
        if (row_hit) {
          hit_rowgroups.push_back(get_pre_rowgroup(it->addr_vec));
          DEBUG_PRINT("added hit rowgroup " << get_string_addr(hit_rowgroups.back()) << " from request " << get_string_addr(it->addr_vec));
        }
      }
      HERE;
      // choose a request that does not close any of the hit rowgroups if possible
      for (auto it = buffer.begin(); it != buffer.end(); ++it) {
        bool is_hit = false;
        if (!has_wildcard(it->addr_vec)) {
          is_hit = m_dram->check_rowbuffer_hit(it->command, it->addr_vec);
        }
        bool violates_hit = false;
        if (!is_hit && m_controller->is_to_open_row(it)) {
          auto rg = get_pre_rowgroup(it->addr_vec);
          for (const auto& hrg: hit_rowgroups) {
            // if request matches row-group that has pending hits
            if (rg == hrg) {
              DEBUG_PRINT("found violating candidate: " << get_string_addr(it->addr_vec));
              violates_hit = true;
              break;
            }
          }
        }
        if (violates_hit) continue;  // skip anything that violates hit preservation

        // if we are here the request is safe (does not violate potential row hits)
        if (candidate == buffer.end()) candidate = it; 
        else candidate = compare_frfcfs(candidate, it);
        DEBUG_PRINT("updated candidate to " << get_string_addr(candidate->addr_vec));
      }
      HERE;
      DEBUG_PRINT("returning candidate " << get_string_addr(candidate->addr_vec));
      return candidate;
    }

      virtual void tick() override {
  }
};

}       // namespace Ramulator
