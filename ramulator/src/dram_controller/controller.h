#ifndef RAMULATOR_CONTROLLER_CONTROLLER_H
#define RAMULATOR_CONTROLLER_CONTROLLER_H

#include <vector>
#include <deque>

#include <spdlog/spdlog.h>
#include <yaml-cpp/yaml.h>

#include "base/base.h"
#include "base/type.h"
#include "dram/dram.h"
#include "dram_controller/scheduler.h"
#include "dram_controller/plugin.h"
#include "dram_controller/refresh.h"
#include "dram_controller/rowpolicy.h"


namespace Ramulator {

class IDRAMController : public Clocked<IDRAMController> {
  RAMULATOR_REGISTER_INTERFACE(IDRAMController, "Controller", "Memory Controller Interface");

  public:
    IDRAM*  m_dram = nullptr;          
    IScheduler*   m_scheduler = nullptr;
    IRefreshManager*   m_refresh = nullptr;
    IRowPolicy*   m_rowpolicy = nullptr;
    std::vector<IControllerPlugin*> m_plugins;
    std::vector<AddrVec_t> blacklist; 
    float s_blacklisted_counter = 0; 
    ReqBuffer m_active_buffer;    

    int m_channel_id = -1;


  public:

  template <class T>
    T* get_plugin() {
      for (auto plugin : m_plugins) {
        T* cast = dynamic_cast<T*>(plugin);
        if (cast) {
          return cast;
        }
      }
      return nullptr;
    }
    /**
     * @brief       Send a request to the memory controller.
     * 
     * @param    req        The request to be enqueued.
     * @return   true       Successful.
     * @return   false      Failed (e.g., buffer full).
     * 
     * 
     */
    virtual bool send(Request& req) = 0;

    virtual void addToBlacklist(Request& req, bool ab) = 0; 

    virtual bool checkBlacklisted(AddrVec_t& address) = 0;

    virtual bool checkBlacklisted(Request& req) {
      return checkBlacklisted(req.addr_vec);
    }

    // Optional QPRAC controller hook.
    virtual bool try_enqueue_qprac_proactive_drfm() {
      return false;
    }

    /**
     * @brief       Send a high-priority request to the memory controller.
     * 
     */
    virtual bool priority_send(Request& req) = 0;

    /**
     * @brief       Ticks the memory controller.
     * 
     */
    virtual void tick() = 0;

    /**
     * @brief       returns true if the request goes to an open row
     * 
     */
    virtual bool is_to_open_row(ReqBuffer::iterator req) = 0; 
   
};

}       // namespace Ramulator

#endif  // RAMULATOR_CONTROLLER_CONTROLLER_H
