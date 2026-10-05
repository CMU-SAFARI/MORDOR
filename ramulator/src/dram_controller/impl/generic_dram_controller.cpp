#include "base/request.h"
#include "base/type.h"
#include "dram_controller/controller.h"
#include "frontend/frontend.h"
#include <iostream>
#include <ostream>

namespace Ramulator {

class GenericDRAMController final : public IDRAMController, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IDRAMController, GenericDRAMController, "Generic", "A generic DRAM controller.");

  private:
    std::deque<Request> pending;          // A queue for read requests that are about to finish (callback after RL)

    ReqBuffer m_active_buffer;            // Buffer for requests being served. This has the highest priority 
    ReqBuffer m_priority_buffer;          // Buffer for high-priority requests (e.g., maintenance like refresh).
    ReqBuffer m_read_buffer;              // Read request buffer
    ReqBuffer m_write_buffer;             // Write request buffer

    //std::map<AddrVec_t, int> s_activation_counts;   // keeps track of how many times a row is activated after it was blacklisted
    int s_max_act_count = 0;

    int m_bank_addr_idx = -1;

    float m_wr_low_watermark;
    float m_wr_high_watermark;
    bool  m_is_write_mode = false;

    size_t s_row_hits = 0;
    size_t s_row_misses = 0;
    size_t s_row_conflicts = 0;
    size_t s_read_row_hits = 0;
    size_t s_read_row_misses = 0;
    size_t s_read_row_conflicts = 0;
    size_t s_write_row_hits = 0;
    size_t s_write_row_misses = 0;
    size_t s_write_row_conflicts = 0;

    size_t m_num_cores = 0;
    std::vector<size_t> s_read_row_hits_per_core;
    std::vector<size_t> s_read_row_misses_per_core;
    std::vector<size_t> s_read_row_conflicts_per_core;

    size_t s_num_read_reqs = 0;
    size_t s_num_write_reqs = 0;
    size_t s_num_other_reqs = 0;
    size_t s_queue_len = 0;
    size_t s_read_queue_len = 0;
    size_t s_write_queue_len = 0;
    size_t s_priority_queue_len = 0;
    float s_queue_len_avg = 0;
    float s_read_queue_len_avg = 0;
    float s_write_queue_len_avg = 0;
    float s_priority_queue_len_avg = 0;

    size_t s_read_latency = 0;
    float s_avg_read_latency = 0;

    // read latency stats
    double s_avg_latency = 0; 
    int s_max_latency = 0; 
    unsigned long long num_reads_issued = 0; 
    unsigned long long current_sum_latency = 0; 


    // memory system reference to count the number of DRFM refreshes
    IMemorySystem* m_system = nullptr; 



  public:
    std::vector<AddrVec_t> blacklist; 
    std::vector<Request> blacklist_buffer; 
    float s_blacklisted_counter = 0; 
    float s_blacklist_max_length = 0; 

    // Function to add an address to the blacklist
    void addToBlacklist(Request& req, bool ab) override {
      AddrVec_t address = req.addr_vec;
      float l = blacklist.size(); 
      if (l>s_blacklist_max_length) s_blacklist_max_length = l; 

      if (!isAddressBlacklisted(address)) {
        blacklist.push_back(address);
        s_blacklisted_counter++;

      }
    }


    void init() override {
      m_wr_low_watermark =  param<float>("wr_low_watermark").desc("Threshold for switching back to read mode.").default_val(0.2f);
      m_wr_high_watermark = param<float>("wr_high_watermark").desc("Threshold for switching to write mode.").default_val(0.8f);

      m_scheduler = create_child_ifce<IScheduler>();
      m_refresh = create_child_ifce<IRefreshManager>();    
      m_rowpolicy = create_child_ifce<IRowPolicy>();    

      if (m_config["plugins"]) {
        YAML::Node plugin_configs = m_config["plugins"];
        for (YAML::iterator it = plugin_configs.begin(); it != plugin_configs.end(); ++it) {
          m_plugins.push_back(create_child_ifce<IControllerPlugin>(*it));
        }
      }
      register_stat(s_avg_latency).name("average_latency");
      register_stat(s_max_latency).name("max_latency");
    };

    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
      m_dram = memory_system->get_ifce<IDRAM>();
      m_bank_addr_idx = m_dram->m_levels("bank");
     // m_priority_buffer.max_size = 10000000;

      m_num_cores = frontend->get_num_cores();

      s_read_row_hits_per_core.resize(m_num_cores, 0);
      s_read_row_misses_per_core.resize(m_num_cores, 0);
      s_read_row_conflicts_per_core.resize(m_num_cores, 0);

      m_system = memory_system;

      register_stat(s_row_hits).name("row_hits_{}", m_channel_id);
      register_stat(s_row_misses).name("row_misses_{}", m_channel_id);
      register_stat(s_row_conflicts).name("row_conflicts_{}", m_channel_id);
      register_stat(s_read_row_hits).name("read_row_hits_{}", m_channel_id);
      register_stat(s_read_row_misses).name("read_row_misses_{}", m_channel_id);
      register_stat(s_read_row_conflicts).name("read_row_conflicts_{}", m_channel_id);
      register_stat(s_write_row_hits).name("write_row_hits_{}", m_channel_id);
      register_stat(s_write_row_misses).name("write_row_misses_{}", m_channel_id);
      register_stat(s_write_row_conflicts).name("write_row_conflicts_{}", m_channel_id);
      register_stat(s_max_act_count).name("max_number_of_acts_after_blacklisting", m_channel_id); 

      for (size_t core_id = 0; core_id < m_num_cores; core_id++) {
        register_stat(s_read_row_hits_per_core[core_id]).name("read_row_hits_core_{}", core_id);
        register_stat(s_read_row_misses_per_core[core_id]).name("read_row_misses_core_{}", core_id);
        register_stat(s_read_row_conflicts_per_core[core_id]).name("read_row_conflicts_core_{}", core_id);
      }

      register_stat(s_num_read_reqs).name("num_read_reqs_{}", m_channel_id);
      register_stat(s_num_write_reqs).name("num_write_reqs_{}", m_channel_id);
      register_stat(s_num_other_reqs).name("num_other_reqs_{}", m_channel_id);
      register_stat(s_queue_len).name("queue_len_{}", m_channel_id);
      register_stat(s_read_queue_len).name("read_queue_len_{}", m_channel_id);
      register_stat(s_write_queue_len).name("write_queue_len_{}", m_channel_id);
      register_stat(s_priority_queue_len).name("priority_queue_len_{}", m_channel_id);
      register_stat(s_queue_len_avg).name("queue_len_avg_{}", m_channel_id);
      register_stat(s_read_queue_len_avg).name("read_queue_len_avg_{}", m_channel_id);
      register_stat(s_write_queue_len_avg).name("write_queue_len_avg_{}", m_channel_id);
      register_stat(s_priority_queue_len_avg).name("priority_queue_len_avg_{}", m_channel_id);

      register_stat(s_read_latency).name("read_latency_{}", m_channel_id);
      register_stat(s_avg_read_latency).name("avg_read_latency_{}", m_channel_id);
      register_stat(s_blacklisted_counter).name("number_of_blacklists{}", m_channel_id);
      register_stat(s_blacklist_max_length).name("max_blacklist_length_{}", m_channel_id); 
    };

    bool send(Request& req) override {
      req.final_command = m_dram->m_request_translations(req.type_id);
      m_system->inc_req_count(req); 

      // Forward existing write requests to incoming read requests
      if (req.type_id == Request::Type::Read) {
        auto compare_addr = [req](const Request& wreq) {
          return wreq.addr == req.addr;
        };
        if (std::find_if(m_write_buffer.begin(), m_write_buffer.end(), compare_addr) != m_write_buffer.end()) {
          // The request will depart at the next cycle
          req.depart = m_clk + 1;
          pending.push_back(req);
          return true;
        }
      }

      // Else, enqueue them to corresponding buffer based on request type id
      bool is_success = false;
      req.arrive = m_clk;

      if ((req.type_id == Request::Type::Read || req.type_id == m_dram->m_requests("same-bank-directed-rfm") || req.type_id == m_dram->m_requests("directed-rfm"))) {
        is_success = m_read_buffer.enqueue(req);
        // print debugging -> TODO: remove later
        //if (!is_success) std::cout  << "request not accepted to read buffer" << std::endl; 
        //else std::cout << "request accepted to read buffer" << std::endl; 
        // remove ends here
      } else if (req.type_id == Request::Type::Write) {
        is_success = m_write_buffer.enqueue(req);
      } else {
        throw std::runtime_error("Invalid request type!" + std::to_string(req.type_id));
        //is_success = m_read_buffer.enqueue(req);
      }
      if (!is_success) {
        // We could not enqueue the request
        req.arrive = -1;
        return false;
      }

      return true;
    };

    bool priority_send(Request& req) override {
      req.final_command = m_dram->m_request_translations(req.type_id);

      bool is_success = false;
      req.arrive = m_clk;
      is_success = m_priority_buffer.enqueue(req);
      // print debugging -> TODO: remove later

      //if (!is_success) std::cout  << "request NOT accepted to prioriry buffer, buffer length is: " << m_priority_buffer.size() << ", Request type is: " << req.type_id << std::endl; 
      //else std::cout << "request accepted to priority buffer, buffer length is: " << m_priority_buffer.size() << ", Request type is: " << req.type_id << std::endl; 
      // remove ends here
      if (!is_success) {
        // We could not enqueue the request
        req.arrive = -1;
        return false;
      } 
      m_system->inc_req_count(req); 
      return is_success;
    }

    // returns true if address is in blacklist
    bool isInBlacklist(const std::vector<AddrVec_t>& blacklist, const AddrVec_t& element) {
      return std::find(blacklist.begin(), blacklist.end(), element) != blacklist.end();
    }


    void tick() override {
      m_clk++;

      // Update statistics
      s_queue_len += m_read_buffer.size() + m_write_buffer.size() + m_priority_buffer.size() + pending.size();
      s_read_queue_len += m_read_buffer.size() + pending.size();
      s_write_queue_len += m_write_buffer.size();
      s_priority_queue_len += m_priority_buffer.size();

      // 1. Serve completed reads
      serve_completed_reads();

      m_refresh->tick();

      bool do_not_issue = false; 
      bool issued_from_buffer = false; 

      // 2. Try to find a request to serve.

      // check if there are requests in the blacklist buffer that are no longer blacklisted
      if (!blacklist_buffer.empty()) {
        //std::cout << "checking blacklist buffer" << std::endl; 
        // if request buffer holds request to address that is no longer blacklisted, issue that request
        for(auto& element : blacklist_buffer) {
          if (!isInBlacklist(blacklist, element.addr_vec)) {
            // enqueue the request since no longer blacklisted
            priority_send(element); 
            //issued_from_buffer = true; 
          }
        }
      }

      if (!issued_from_buffer) {
        ReqBuffer::iterator req_it;
        ReqBuffer* buffer = nullptr;
        bool request_found = schedule_request(req_it, buffer);

        // 2.1 Take row policy action
        m_rowpolicy->update(request_found, req_it);



        // 3. Update all plugins
        if (! request_found) {
        // no request found, no need to check for blacklisted
          for (auto plugin : m_plugins) {
            plugin->update(request_found, req_it);
          }
        }
      

        // 4. Finally, issue the commands to serve the request
        if (request_found) {

          //check if address is blacklisted
          bool blacklisted = isAddressBlacklisted(req_it->addr_vec);

          // blacklisted and not DRFM request
          if (blacklisted&& !(req_it->type_id == m_dram->m_requests("same-bank-directed-rfm"))) {
            // add to blacklist buffer, don't issue yet
            blacklist_buffer.push_back(*req_it); 
            buffer->remove(req_it);

            //should we do this?
            do_not_issue = true; 

            //increment ativation counter 
            /*
            auto it = s_activation_counts.find(req_it->addr_vec);
            if (it != s_activation_counts.end()) {
              // Key exists, increment the value
              it->second++;
            } else {
              // Key does not exist, insert with initial value 1
              s_activation_counts[req_it->addr_vec] = 1;
            }*/

            // update plugin without request, since we did not issue it
            for (auto plugin : m_plugins) {
              plugin->update(false, req_it);
            }

          // DRFM request is issued to blacklisted row -> need to unblacklist
          } else if (req_it->type_id == m_dram->m_requests("same-bank-directed-rfm")) {
            // unblacklist the address if DRFM will be issued next
            auto it = std::find(blacklist.begin(), blacklist.end(), req_it->addr_vec);
            if (it != blacklist.end()) {
              blacklist.erase(it);
            }

            // update max activation counter, reset act counter for that address
            /*auto it2 = s_activation_counts.find(req_it->addr_vec);
            if (it2 != s_activation_counts.end()) {
              // Key exists, increment the value
              int activations = it2->second; 
              if (activations > s_max_act_count) s_max_act_count = activations; 
              it2->second = 0;
            } */
          }
        
          if (!do_not_issue) {
            // update plugin with request, since we're about to issue it
            for (auto plugin : m_plugins) {
              plugin->update(request_found, req_it);
            }


            // 4. Finally, issue the commands to serve the request
            // If we find a real request to serve
            if (req_it->is_stat_updated == false) {
              update_request_stats(req_it);
            }

            m_dram->issue_command(req_it->command, req_it->addr_vec); 


            // If we are issuing the last command, set depart clock cycle and move the request to the pending queue
            if (req_it->command == req_it->final_command) {
              if (req_it->type_id == Request::Type::Read) {
                req_it->depart = m_clk + m_dram->m_read_latency;
                pending.push_back(*req_it);
              } else if (req_it->type_id == Request::Type::Write) {
                // TODO: Add code to update statistics
              } 

              buffer->remove(req_it);


            } else {
              if (m_dram->m_command_meta(req_it->command).is_opening ) {
                m_active_buffer.enqueue(*req_it);
                buffer->remove(req_it);
              } 
            }
          } // end !do_not_issue
        } // end request found
      } // end !issued_from_buffer
    };

    bool isAddressBlacklisted(AddrVec_t address) {
      for (const auto& item : blacklist) {
        if (item == address) {
            return true;
        }
      }
      return false;
    }


  private:
    /**
     * @brief    Helper function to check if a request is hitting an open row
     * @details
     * 
     */
    bool is_row_hit(ReqBuffer::iterator& req)
    {
        return m_dram->check_rowbuffer_hit(req->final_command, req->addr_vec);
    }
    /**
     * @brief    Helper function to check if a request is opening a row
     * @details
     * 
    */
    bool is_row_open(ReqBuffer::iterator& req)
    {
        return m_dram->check_node_open(req->final_command, req->addr_vec);
    }

    bool is_to_open_row(ReqBuffer::iterator req) override {
      for (auto it = m_active_buffer.begin(); it != m_active_buffer.end(); ++it) {
        if (it == req)
          return true;
      }
      return false;
    }

    /**
     * @brief    
     * @details
     * 
     */
    void update_request_stats(ReqBuffer::iterator& req)
    {
      req->is_stat_updated = true;

      if (req->type_id == Request::Type::Read) 
      {
        if (is_row_hit(req)) {
          s_read_row_hits++;
          s_row_hits++;
          if (req->source_id != -1)
            s_read_row_hits_per_core[req->source_id]++;
        } else if (is_row_open(req)) {
          s_read_row_conflicts++;
          s_row_conflicts++;
          if (req->source_id != -1)
            s_read_row_conflicts_per_core[req->source_id]++;
        } else {
          s_read_row_misses++;
          s_row_misses++;
          if (req->source_id != -1)
            s_read_row_misses_per_core[req->source_id]++;
        } 
      } 
      else if (req->type_id == Request::Type::Write) 
      {
        if (is_row_hit(req)) {
          s_write_row_hits++;
          s_row_hits++;
        } else if (is_row_open(req)) {
          s_write_row_conflicts++;
          s_row_conflicts++;
        } else {
          s_write_row_misses++;
          s_row_misses++;
        }
      }
    }

    /**
     * @brief    Helper function to serve the completed read requests
     * @details
     * This function is called at the beginning of the tick() function.
     * It checks the pending queue to see if the top request has received data from DRAM.
     * If so, it finishes this request by calling its callback and poping it from the pending queue.
     */
    void serve_completed_reads() {
      if (pending.size()) {
        // Check the first pending request
        auto& req = pending[0];
        if (req.depart <= m_clk) {
          // Request received data from dram
          if (req.depart - req.arrive > 1) {
            if (req.depart < 0 || req.arrive < 0 || req.depart < req.arrive) {
              //std::cout << "Invalid parameters: depart: " << req.depart << ", arrive: "  << req.arrive << std::endl;
            } else {
                // Check if this requests accesses the DRAM or is being forwarded.
              if (req.type_id == Request::Type::Read) {
                // compute running average and max latency for issued read requests
                num_reads_issued++; 
                int latency = req.depart - req.arrive; 
              
                // Check for overflow before updating the sum
                if (current_sum_latency <= ULLONG_MAX - latency) {
                    current_sum_latency += latency;
                    s_avg_latency = static_cast<double>(current_sum_latency) / num_reads_issued;
                } else {
                    //std::cout << "Overflow detected in latency sum calculation!" << std::endl;
                }
                if (latency > s_max_latency) s_max_latency = latency;  // update maximum latency
                //std::cout << "Read arrive: " << req.arrive <<", depart: " << req.depart << ", latency: " << latency << std::endl; 
              }
            }
            s_read_latency += req.depart - req.arrive;
          }

          if (req.callback) {
            // If the request comes from outside (e.g., processor), call its callback
            req.callback(req);
          }
          // Finally, remove this request from the pending queue
          pending.pop_front();
        }
      };
    };


    /**
     * @brief    Checks if we need to switch to write mode
     * 
     */
    void set_write_mode() {
      if (!m_is_write_mode) {
        if ((m_write_buffer.size() > m_wr_high_watermark * m_write_buffer.max_size) || m_read_buffer.size() == 0) {
          m_is_write_mode = true;
        }
      } else {
        if ((m_write_buffer.size() < m_wr_low_watermark * m_write_buffer.max_size) && m_read_buffer.size() != 0) {
          m_is_write_mode = false;
        }
      }
    };


    /**
     * @brief    Helper function to find a request to schedule from the buffers.
     * 
     */
    bool schedule_request(ReqBuffer::iterator& req_it, ReqBuffer*& req_buffer) {
      bool request_found = false;
      // 2.1    First, check the act buffer to serve requests that are already activating (avoid useless ACTs)
      if (req_it= m_scheduler->get_best_request(m_active_buffer); req_it != m_active_buffer.end()) {
        if (m_dram->check_ready(req_it->command, req_it->addr_vec)) {
          request_found = true;
          req_buffer = &m_active_buffer;
        }
      }

      // 2.2    If no requests can be scheduled from the act buffer, check the rest of the buffers
      if (!request_found) {
        // 2.2.1    We first check the priority buffer to prioritize e.g., maintenance requests
        if (m_priority_buffer.size() != 0) {
          req_buffer = &m_priority_buffer;
          req_it = m_priority_buffer.begin();
          req_it->command = m_dram->get_preq_command(req_it->final_command, req_it->addr_vec);
          
          request_found = m_dram->check_ready(req_it->command, req_it->addr_vec);
          
          if (!request_found & (m_priority_buffer.size() != 0)) {
            return false;
          }
        }

        // 2.2.1    If no request to be scheduled in the priority buffer, check the read and write buffers.
        if (!request_found) {
          // Query the write policy ramulator2/to decide which buffer to serve
          set_write_mode();
          auto& buffer = m_is_write_mode ? m_write_buffer : m_read_buffer;
          if (req_it = m_scheduler->get_best_request(buffer); req_it != buffer.end()) {
            request_found = m_dram->check_ready(req_it->command, req_it->addr_vec);
            req_buffer = &buffer;
          }
        }
      }

      // 2.3 If we find a request to schedule, we need to check if it will close an opened row in the active buffer.
      if (request_found) {
        if (m_dram->m_command_meta(req_it->command).is_closing) {
          auto& rowgroup = req_it->addr_vec;
          for (auto _it = m_active_buffer.begin(); _it != m_active_buffer.end(); _it++) {
            auto& _it_rowgroup = _it->addr_vec;
            bool is_matching = true;
            for (int i = 0; i < m_bank_addr_idx + 1 ; i++) {
              if (_it_rowgroup[i] != rowgroup[i] && _it_rowgroup[i] != -1 && rowgroup[i] != -1) {
                is_matching = false;
                break;
              }
            }
            if (is_matching) {
              request_found = false;
              break;
            }
          }
        }
      }

      return request_found;
    }

    void finalize() override {
      s_avg_read_latency = (float) s_read_latency / (float) s_num_read_reqs;

      s_queue_len_avg = (float) s_queue_len / (float) m_clk;
      s_read_queue_len_avg = (float) s_read_queue_len / (float) m_clk;
      s_write_queue_len_avg = (float) s_write_queue_len / (float) m_clk;
      s_priority_queue_len_avg = (float) s_priority_queue_len / (float) m_clk;

      return;
    }

    bool checkBlacklisted(AddrVec_t& address) {return false;}

};
  
}   // namespace Ramulator
