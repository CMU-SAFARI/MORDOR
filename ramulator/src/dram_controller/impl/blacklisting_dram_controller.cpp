#include "base/request.h"
#include "base/type.h"
#include "dram/spec.h"
#include "dram_controller/controller.h"
#include "frontend/frontend.h"

#include <climits>
#include <cstddef>
#include <deque>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

namespace Ramulator {

class BlacklistingDRAMController final : public IDRAMController,
                                         public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(
      IDRAMController, BlacklistingDRAMController, "Blacklisting",
      "A DRAM controller that uses aggressor row blacklisting.");

private:
  std::deque<Request> pending; // A queue for read requests that are about to
                               // finish (callback after RL)

  ReqBuffer m_priority_buffer; // Buffer for high-priority requests (e.g.,
                               // maintenance like refresh).
  ReqBuffer m_read_buffer;     // Read request buffer
  ReqBuffer m_write_buffer;    // Write request buffer

  int s_max_act_count = 0;

  int m_bank_addr_idx = -1;
  int m_col_addr_idx = -1;

  float m_wr_low_watermark;
  float m_wr_high_watermark;
  bool m_is_write_mode = false;
  int m_log_request_latencies = 0;

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

  size_t demand_delayed_by_PRO = 0;
  float avg_num_demand_delayed_by_PRO = 0;
  size_t read_demand_delayed_by_PRO = 0;
  float avg_num_read_demand_delayed_by_PRO = 0;
  size_t write_demand_delayed_by_PRO = 0;
  float avg_num_write_demand_delayed_by_PRO = 0;
  size_t num_counted_PROs = 0;
  int max_num_demand_delayed_by_PRO = 0;
  int max_num_read_demand_delayed_by_PRO = 0;
  int max_num_write_demand_delayed_by_PRO = 0;

  size_t s_read_latency = 0;
  float s_avg_read_latency = 0;
  float s_max_read_latency = 0;

  // read latency stats
  double s_avg_latency = 0;
  unsigned long long num_reads_issued = 0;
  unsigned long long current_sum_latency = 0;

  // PROQ stats
  float s_num_proq_adds = 0;
  float s_num_proq_remv = 0;
  float s_avg_proq_time = -1;
  float s_total_proq_time = 0;
  float s_max_proq_time = 0;
  float s_min_proq_time = -1;
  size_t s_num_early_pros_due_to_proq_occupancy = 0;
  size_t s_num_rd_proq_adds = 0;
  size_t s_num_rd_proq_removes = 0;
  size_t s_num_wr_proq_adds = 0;
  size_t s_num_wr_proq_removes = 0;
  size_t s_current_rd_proq_entries = 0;
  size_t s_max_rd_proq_entries = 0;
  size_t s_current_wr_proq_entries = 0;
  size_t s_max_wr_proq_entries = 0;
  size_t s_num_capacity_promotions_rd = 0;
  size_t s_num_capacity_promotions_wr = 0;
  size_t s_num_capacity_promotions_pro = 0;

  int not_found_req = 0;

  // Historical default: promote at 30 entries (a 32-entry target with two
  // entries reserved for PROs caused by the PRO at the head).
  static constexpr size_t k_default_proq_occupancy_promotion_threshold = 30;
  size_t m_proq_occupancy_promotion_threshold =
      k_default_proq_occupancy_promotion_threshold;
  bool m_drain_proq_from_tail = false;
  bool m_occupancy_promoted_request_pending = false;
  bool m_occupancy_promoted_from_tail = false;
  AddrVec_t m_occupancy_promoted_addr;
  Request::MitigationType m_occupancy_promoted_type =
      Request::MitigationType::None;

  IMemorySystem *m_system = nullptr;

  // PROQ stats:
  float s_max_blacklist_size = 0;
  float s_avg_blacklist_size = 0;
  float s_blacklist_len = 0;

  #ifdef DEBUG
    #define HERE std::cout << "[HERE] " << __FILE__ << ":" << __FUNCTION__ << ":" << __LINE__ << std::endl
    #define DEBUG_PRINT(x) std::cout << "MC: " << x << std::endl
  #else
    #define DEBUG_PRINT(x)
    #define HERE
  #endif

  std::string get_string_addr(const AddrVec_t& addr) {
    std::ostringstream a;
    for (size_t i=0; i<addr.size(); ++i) {
      a << addr[i];
    }
    return a.str();
  }

public:
  // Public because the blacklisting scheduler checks the active buffer.
  ReqBuffer m_active_buffer;

  struct TrackedPROQEntry {
    AddrVec_t addr_vec;
    Request::MitigationType type;
  };
  std::vector<TrackedPROQEntry> blacklist;
  std::vector<Request> blacklist_buffer;
  float s_blacklisted_counter = 0;
  float s_blacklist_max_length = 0;

  float num_cycle_no_request_found = 0;

  bool addresses_overlap(const AddrVec_t& lhs, const AddrVec_t& rhs) const {
    if (lhs.size() != rhs.size()) return false;
    for (size_t i = 0; i < lhs.size(); i++) {
      if (lhs[i] != -1 && rhs[i] != -1 && lhs[i] != rhs[i]) return false;
    }
    return true;
  }

  AddrVec_t metadata_row_address(const Request& req) const {
    AddrVec_t addr = req.addr_vec;
    addr[m_col_addr_idx] = -1;
    return addr;
  }

  bool request_matches_entry(const Request& req,
                             const TrackedPROQEntry& entry) const {
    return req.mitigation_type == entry.type &&
           addresses_overlap(req.addr_vec, entry.addr_vec);
  }

  void update_typed_proq_add_stats(Request::MitigationType type) {
    if (type == Request::MitigationType::RD) {
      s_num_rd_proq_adds++;
      s_current_rd_proq_entries++;
      s_max_rd_proq_entries =
          std::max(s_max_rd_proq_entries, s_current_rd_proq_entries);
    } else if (type == Request::MitigationType::WR) {
      s_num_wr_proq_adds++;
      s_current_wr_proq_entries++;
      s_max_wr_proq_entries =
          std::max(s_max_wr_proq_entries, s_current_wr_proq_entries);
    }
  }

  void add_accepted_metadata_to_proq(Request& req) {
    if (req.mitigation_type != Request::MitigationType::RD &&
        req.mitigation_type != Request::MitigationType::WR) {
      return;
    }
    // Hydra tracking reads and writes are mitigation operations. This model
    // treats them as PROs for scheduling, PROQ occupancy, and PRO-intensity
    // accounting. Separating metadata traffic from PROs is left to a future
    // detailed sensitivity study.
    blacklist.push_back({metadata_row_address(req), req.mitigation_type});
    s_num_proq_adds++;
    update_typed_proq_add_stats(req.mitigation_type);
    s_max_blacklist_size = std::max<float>(s_max_blacklist_size,
                                            blacklist.size());
  }

  bool remove_one_metadata_proq_entry(const Request& req) {
    for (auto it = blacklist.begin(); it != blacklist.end(); ++it) {
      if (request_matches_entry(req, *it)) {
        if (it->type == Request::MitigationType::RD) {
          s_num_rd_proq_removes++;
          s_current_rd_proq_entries--;
        } else if (it->type == Request::MitigationType::WR) {
          s_num_wr_proq_removes++;
          s_current_wr_proq_entries--;
        }
        if (req.proq_enc >= 0) {
          float time_in_proq = m_clk - req.proq_enc;
          s_total_proq_time += time_in_proq;
          s_max_proq_time = std::max(s_max_proq_time, time_in_proq);
          if (s_min_proq_time == -1 || time_in_proq < s_min_proq_time) {
            s_min_proq_time = time_in_proq;
          }
        }
        blacklist.erase(it);
        s_num_proq_remv++;
        return true;
      }
    }
    return false;
  }

  void addToBlacklist(Request& req, bool ab) override {
    req.mitigation_type = Request::MitigationType::PRO;
    req.proq_enc = m_clk;
    AddrVec_t address = req.addr_vec;
    float l = blacklist.size();
    if (l > s_blacklist_max_length)
      s_blacklist_max_length = l;

    int m_bank_group_level = m_dram->m_levels("bankgroup");
    AddrVec_t addr = address;
    addr[m_bank_group_level] = -1;

    bool already_tracked = std::any_of(
        blacklist.begin(), blacklist.end(), [&](const TrackedPROQEntry& entry) {
          return entry.type == Request::MitigationType::PRO &&
                 entry.addr_vec == addr;
        });
    if (!already_tracked) {
      blacklist.push_back({addr, Request::MitigationType::PRO});
      s_num_proq_adds += 1;
    }

    if (blacklist.size() > s_max_blacklist_size) {
      s_max_blacklist_size = blacklist.size();
    }
  }

  void init() override {
    int configured_proq_occupancy_threshold =
        param<int>("proq_occupancy_promotion_threshold")
            .desc("Number of PROQ entries that triggers occupancy-based PRO promotion.")
            .default_val(k_default_proq_occupancy_promotion_threshold);
    if (configured_proq_occupancy_threshold <= 0) {
      throw std::runtime_error(
          "proq_occupancy_promotion_threshold must be greater than zero");
    }
    m_proq_occupancy_promotion_threshold =
        static_cast<size_t>(configured_proq_occupancy_threshold);
    m_wr_low_watermark = param<float>("wr_low_watermark")
                             .desc("Threshold for switching back to read mode.")
                             .default_val(0.2f);
    m_wr_high_watermark = param<float>("wr_high_watermark")
                              .desc("Threshold for switching to write mode.")
                              .default_val(0.8f);
    m_log_request_latencies = param<int>("log_request_latencies")
                                  .desc("Print completed read and PRO request latencies.")
                                  .default_val(0);
    m_scheduler = create_child_ifce<IScheduler>();
    m_refresh = create_child_ifce<IRefreshManager>();
    m_rowpolicy = create_child_ifce<IRowPolicy>();

    if (m_config["plugins"]) {
      YAML::Node plugin_configs = m_config["plugins"];
      for (YAML::iterator it = plugin_configs.begin();
           it != plugin_configs.end(); ++it) {
        m_plugins.push_back(create_child_ifce<IControllerPlugin>(*it));
      }
    }
    register_stat(s_avg_latency).name("average_latency");
    register_stat(s_max_read_latency).name("max__read_latency");
  };

  void setup(IFrontEnd *frontend, IMemorySystem *memory_system) override {
    m_dram = memory_system->get_ifce<IDRAM>();
    m_bank_addr_idx = m_dram->m_levels("bank");
    m_col_addr_idx = m_dram->m_levels("column");
    m_priority_buffer.max_size = 32;

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
    register_stat(s_read_row_conflicts)
        .name("read_row_conflicts_{}", m_channel_id);
    register_stat(s_write_row_hits).name("write_row_hits_{}", m_channel_id);
    register_stat(s_write_row_misses).name("write_row_misses_{}", m_channel_id);
    register_stat(s_write_row_conflicts)
        .name("write_row_conflicts_{}", m_channel_id);
    register_stat(s_max_act_count)
        .name("max_number_of_acts_after_blacklisting", m_channel_id);

    for (size_t core_id = 0; core_id < m_num_cores; core_id++) {
      register_stat(s_read_row_hits_per_core[core_id])
          .name("read_row_hits_core_{}", core_id);
      register_stat(s_read_row_misses_per_core[core_id])
          .name("read_row_misses_core_{}", core_id);
      register_stat(s_read_row_conflicts_per_core[core_id])
          .name("read_row_conflicts_core_{}", core_id);
    }

    register_stat(s_num_read_reqs).name("num_read_reqs_{}", m_channel_id);
    register_stat(s_num_write_reqs).name("num_write_reqs_{}", m_channel_id);
    register_stat(s_num_other_reqs).name("num_other_reqs_{}", m_channel_id);
    register_stat(s_queue_len).name("queue_len_{}", m_channel_id);
    register_stat(s_read_queue_len).name("read_queue_len_{}", m_channel_id);
    register_stat(s_write_queue_len).name("write_queue_len_{}", m_channel_id);
    register_stat(s_priority_queue_len)
        .name("priority_queue_len_{}", m_channel_id);
    register_stat(s_queue_len_avg).name("queue_len_avg_{}", m_channel_id);
    register_stat(s_read_queue_len_avg)
        .name("read_queue_len_avg_{}", m_channel_id);
    register_stat(s_write_queue_len_avg)
        .name("write_queue_len_avg_{}", m_channel_id);
    register_stat(s_priority_queue_len_avg)
        .name("priority_queue_len_avg_{}", m_channel_id);

    register_stat(s_read_latency).name("read_latency_{}", m_channel_id);
    register_stat(s_avg_read_latency).name("avg_read_latency_{}", m_channel_id);
    register_stat(s_blacklisted_counter)
        .name("number_of_blacklists{}", m_channel_id);
    register_stat(s_blacklist_max_length)
        .name("max_blacklist_length_{}", m_channel_id);
    register_stat(s_blacklist_max_length).name("max_PROQ_size");
    register_stat(s_avg_blacklist_size).name("avg_PROQ_size");

    register_stat(s_avg_proq_time).name("avg_PROQ_time");
    register_stat(s_total_proq_time).name("total_PROQ_time");
    register_stat(s_max_proq_time).name("max_PROQ_time");
    register_stat(s_num_proq_adds).name("num_PROQ_adds");
    register_stat(s_num_proq_remv).name("num_PROQ_remove");
    register_stat(s_min_proq_time).name("min_PROQ_time");
    register_stat(s_num_early_pros_due_to_proq_occupancy)
        .name("num_early_PROs_due_to_PROQ_occupancy");
    register_stat(s_num_rd_proq_adds).name("num_RD_PROQ_adds");
    register_stat(s_num_rd_proq_removes).name("num_RD_PROQ_removes");
    register_stat(s_num_wr_proq_adds).name("num_WR_PROQ_adds");
    register_stat(s_num_wr_proq_removes).name("num_WR_PROQ_removes");
    register_stat(s_current_rd_proq_entries).name("current_RD_PROQ_entries");
    register_stat(s_max_rd_proq_entries).name("max_RD_PROQ_entries");
    register_stat(s_current_wr_proq_entries).name("current_WR_PROQ_entries");
    register_stat(s_max_wr_proq_entries).name("max_WR_PROQ_entries");
    register_stat(s_num_capacity_promotions_rd)
        .name("num_capacity_promotions_RD");
    register_stat(s_num_capacity_promotions_wr)
        .name("num_capacity_promotions_WR");
    register_stat(s_num_capacity_promotions_pro)
        .name("num_capacity_promotions_PRO");
    register_stat(m_proq_occupancy_promotion_threshold)
        .name("PROQ_occupancy_promotion_threshold");

    register_stat(avg_num_demand_delayed_by_PRO)
        .name("avg_num_demand_delayed_by_PRO");
    register_stat(num_counted_PROs).name("num_counted_PROs");
    register_stat(max_num_demand_delayed_by_PRO)
        .name("max_num_demand_delayed_by_PRO");
    register_stat(avg_num_read_demand_delayed_by_PRO)
        .name("avg_num_read_demand_delayed_by_PRO");
    register_stat(max_num_read_demand_delayed_by_PRO)
        .name("max_num_read_demand_delayed_by_PRO");
    register_stat(avg_num_write_demand_delayed_by_PRO)
        .name("avg_num_write_demand_delayed_by_PRO");
    register_stat(max_num_write_demand_delayed_by_PRO)
        .name("max_num_write_demand_delayed_by_PRO");

    register_stat(num_cycle_no_request_found).name("num_cycle_no_request_found");
  };

  bool send(Request &req) override {
    // Count processor reads only; mitigation metadata uses source_id == -1.
    if (req.type_id == Request::Type::Read &&
        req.mitigation_type == Request::MitigationType::None &&
        req.source_id >= 0) {
      s_num_read_reqs += 1;
    }

    req.final_command = m_dram->m_request_translations(req.type_id);
    if (req.mitigation_type == Request::MitigationType::RD ||
        req.mitigation_type == Request::MitigationType::WR) {
      req.proq_enc = m_clk;
    }

    // Forward existing write requests to incoming read requests
    if (req.type_id == Request::Type::Read) {
      auto compare_addr = [&req](const Request &wreq) {
        if (req.addr >= 0 && wreq.addr >= 0) {
          return wreq.addr == req.addr;
        }

        // Internally generated requests (e.g., Hydra RCT accesses) are built
        // from an address vector and leave the scalar address at -1. In that
        // case, only forward an exact address-vector match; two unavailable
        // scalar addresses do not identify the same memory location.
        return !req.addr_vec.empty() && !wreq.addr_vec.empty() &&
               wreq.addr_vec == req.addr_vec;
      };
      if (std::find_if(m_write_buffer.begin(), m_write_buffer.end(),
                       compare_addr) != m_write_buffer.end()) {
        req.arrive = m_clk;
        req.depart = m_clk + 1;
        pending.push_back(req);
        add_accepted_metadata_to_proq(req);
        m_system->inc_req_count(req);
        return true;
      }
    }

    bool is_success = false;
    req.arrive = m_clk;
    if ((req.type_id == Request::Type::Read ||
         req.type_id == m_dram->m_requests("same-bank-directed-rfm") ||
         req.type_id == m_dram->m_requests("directed-rfm"))) {
      is_success = m_read_buffer.enqueue(req);
    } else if (req.type_id == Request::Type::Write) {
      is_success = m_write_buffer.enqueue(req);
    } else {
      throw std::runtime_error("Invalid request type!" +
                               std::to_string(req.type_id));
    }
    if (!is_success) {
      req.arrive = -1;
      if (req.mitigation_type == Request::MitigationType::RD ||
          req.mitigation_type == Request::MitigationType::WR) {
        req.proq_enc = -1;
      }
      return false;
    }
    add_accepted_metadata_to_proq(req);
    m_system->inc_req_count(req);
    return true;
  };

  bool priority_send(Request &req) override {
    req.final_command = m_dram->m_request_translations(req.type_id);

    bool is_success = false;
    req.arrive = m_clk;
    is_success = m_priority_buffer.enqueue(req);

    if (!is_success) {
      req.arrive = -1;
      return false;
    }
    m_system->inc_req_count(req);
    return is_success;
  }

  bool is_to_open_row(ReqBuffer::iterator req) override {
    for (auto it = m_active_buffer.begin(); it != m_active_buffer.end(); ++it) {
      if (it == req)
        return true;
    }
    return false;
  }

  void tick() override {
    m_clk++;

    // Move at most one occupancy-selected mitigation request into the priority
    // queue. Wait until it issues before choosing the next head/tail entry.
    prioritize_proq_for_occupancy();

    if (s_blacklist_max_length < blacklist.size()) s_blacklist_max_length = blacklist.size();

    // Update statistics
    s_queue_len += m_read_buffer.size() + m_write_buffer.size() +
                   m_priority_buffer.size() + pending.size();
    s_read_queue_len += m_read_buffer.size() + pending.size();
    s_write_queue_len += m_write_buffer.size();
    s_priority_queue_len += m_priority_buffer.size();
    s_blacklist_len += blacklist.size();

    // 1. Serve completed reads
    serve_completed_reads();

    m_refresh->tick();

    // 2. Try to find a request to serve.
    ReqBuffer::iterator req_it;
    ReqBuffer *buffer = nullptr;
    bool request_found = schedule_request(req_it, buffer);

    // 2.1 Take row policy action
    m_rowpolicy->update(request_found, req_it);

    // 3. Update all plugins
    if (!request_found) {
      // no request found, no need to check for blacklisted
      for (auto plugin : m_plugins) {
        plugin->update(request_found, req_it);
      }

    }

    // 4. Finally, issue the commands to serve the request
    if (request_found) {
      bool issued_occupancy_promoted_request =
          m_occupancy_promoted_request_pending &&
          req_it->mitigation_type == m_occupancy_promoted_type &&
          addresses_overlap(req_it->addr_vec, m_occupancy_promoted_addr);

      if ((req_it->mitigation_type == Request::MitigationType::RD ||
           req_it->mitigation_type == Request::MitigationType::WR) &&
          req_it->command == req_it->final_command) {
        remove_one_metadata_proq_entry(*req_it);
      }

      // if request is a DRFM, we need to unblacklist the corresponding address
      if (req_it->type_id == m_dram->m_requests("same-bank-directed-rfm")) {
        // unblacklist the address if DRFM will be issued next
        for (auto it = blacklist.begin(); it != blacklist.end();) {
          AddrVec_t addr = it->addr_vec;
          int m_bank_group_level = m_dram->m_levels("bankgroup");
          addr[m_bank_group_level] = -1;
          AddrVec_t addr_v = req_it->addr_vec;
          addr_v[m_bank_group_level] = -1;

          if (it->type == Request::MitigationType::PRO && addr == addr_v) {
            it = blacklist.erase(it);

            // keep track of time spent in PROQ for stats
            s_num_proq_remv+=1;
            req_it->proq_dec = m_clk;
            float time_in_proq = req_it->proq_dec - req_it->proq_enc;
            s_total_proq_time += time_in_proq;
            if (time_in_proq > s_max_proq_time) s_max_proq_time = time_in_proq;
            if (s_min_proq_time == -1) s_min_proq_time = time_in_proq;
            if (s_min_proq_time != -1 && s_min_proq_time>time_in_proq) s_min_proq_time = time_in_proq;
          } else {
            ++it;
          }
        }

      } else if (req_it->type_id == m_dram->m_requests("directed-rfm")){
        // DRFMab request: try to unblacklist the address across all banks (assume 32 banks):
        int m_bank_level = m_dram->m_levels("bank");
        for (int i=0; i<32; i++) {
          for (auto it = blacklist.begin(); it != blacklist.end();) {
            AddrVec_t addr = it->addr_vec;
            int m_bank_group_level = m_dram->m_levels("bankgroup");
            addr[m_bank_group_level] = -1;
            AddrVec_t addr_v = req_it->addr_vec;
            addr_v[m_bank_group_level] = -1;
            addr_v[m_bank_level] = i;

            if (it->type == Request::MitigationType::PRO && addr == addr_v) {
              it = blacklist.erase(it);
              // keep track of time spent in PROQ for stats
              s_num_proq_remv += 1;
              req_it->proq_dec = m_clk;
              float time_in_proq = req_it->proq_dec - req_it->proq_enc;
              s_total_proq_time += time_in_proq;
              if (time_in_proq > s_max_proq_time) s_max_proq_time = time_in_proq;
              if (s_min_proq_time == -1) s_min_proq_time = time_in_proq;
              if (s_min_proq_time != -1 && s_min_proq_time>time_in_proq) s_min_proq_time = time_in_proq;
          } else {
            ++it;
          }
        }
        }

      }

      if (issued_occupancy_promoted_request) {
        if (m_occupancy_promoted_type == Request::MitigationType::PRO) {
          s_num_early_pros_due_to_proq_occupancy += 1;
        }
        m_occupancy_promoted_request_pending = false;
        m_occupancy_promoted_type = Request::MitigationType::None;
        if (m_occupancy_promoted_from_tail) {
          m_drain_proq_from_tail =
              blacklist.size() > m_proq_occupancy_promotion_threshold;
        } else {
          m_drain_proq_from_tail = true;
        }
      }

      // update plugin with request, since we're about to issue it
      for (auto plugin : m_plugins) {
        plugin->update(request_found, req_it);
      }

      // 4. Finally, issue the commands to serve the request
      // If we find a real request to serve
      if (req_it->is_stat_updated == false) {
        update_request_stats(req_it);
      }

      DEBUG_PRINT("about to issue request of type: " << req_it->type_id
          << " to address: " << get_string_addr(req_it->addr_vec));
      m_dram->issue_command(req_it->command, req_it->addr_vec);

      // If we are issuing the last command, set depart clock cycle and move the
      // request to the pending queue
      if (req_it->command == req_it->final_command) {
        if (req_it->type_id == Request::Type::Read) {
          req_it->depart = m_clk + m_dram->m_read_latency;
          pending.push_back(*req_it);
        } else if (req_it->type_id == Request::Type::Write) {
        } else {
          req_it->depart = m_clk + m_dram->m_read_latency;
        }
        // get PRO latency stats
        if (req_it->command == m_dram->m_commands("DRFMsb") ||
            req_it->command == m_dram->m_commands("DRFMab")) {
          int latency = req_it->depart - req_it->arrive;
          if (m_log_request_latencies)
            std::cout << "[Lat (PRO): " << latency << "]" << std::endl;
          DEBUG_PRINT("PRO: arrive: " << req_it->arrive << ", depart: "
              << req_it->depart << ", latency: " << latency);
        }

        buffer->remove(req_it);
      } else {
        if (m_dram->m_command_meta(req_it->command).is_opening) {
          m_active_buffer.enqueue(*req_it);
          buffer->remove(req_it);
        }
      }
    } // end request found
  };

  bool isAddressBlacklisted(const AddrVec_t& address) {
    for (const auto &item : blacklist) {
      if (addresses_overlap(item.addr_vec, address)) {
        return true;
      }
    }
    return false;
  }

  bool checkBlacklisted(AddrVec_t &address) override {
    for (const auto& entry : blacklist) {
      if (addresses_overlap(entry.addr_vec, address)) return true;
    }
    return false;
  }

  bool checkBlacklisted(Request& req) override {
    if (req.mitigation_type != Request::MitigationType::None) return false;
    return checkBlacklisted(req.addr_vec);
  }


private:
  bool is_row_hit(ReqBuffer::iterator &req) {
    return m_dram->check_rowbuffer_hit(req->final_command, req->addr_vec);
  }
  bool is_row_open(ReqBuffer::iterator &req) {
    return m_dram->check_node_open(req->final_command, req->addr_vec);
  }

  void update_request_stats(ReqBuffer::iterator &req) {
    req->is_stat_updated = true;

    if (req->type_id == Request::Type::Read) {
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
    } else if (req->type_id == Request::Type::Write) {
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
   * It checks the pending queue to see if the top request has received data
   * from DRAM. If so, it finishes this request by calling its callback and
   * poping it from the pending queue.
   */
  void serve_completed_reads() {
    if (pending.size()) {
      // Check the first pending request
      auto &req = pending[0];
      if (req.depart <= m_clk) {
        // Request received data from dram
        if (req.depart - req.arrive > 1) {
          if (req.depart < 0 || req.arrive < 0 || req.depart < req.arrive) {
            DEBUG_PRINT("Invalid read timing: depart=" << req.depart
                << ", arrive=" << req.arrive);
          } else {
            // Check if this requests accesses the DRAM or is being forwarded.
            if (req.type_id == Request::Type::Read &&
                req.mitigation_type == Request::MitigationType::None &&
                req.source_id >= 0) {
              // compute running average and max latency for issued read
              // requests. Internally generated mitigation reads (for example,
              // Hydra RCT accesses) use source_id == -1 and must not appear in
              // the demand-read latency distribution.
              num_reads_issued++;
              int latency = req.depart - req.arrive;
              s_read_latency += latency;
              if (m_log_request_latencies)
                std::cout << "[Lat (RD): " << latency << "]" << std::endl;
              DEBUG_PRINT("Read latency: " << latency);

              // Check for overflow before updating the sum
              if (current_sum_latency <= ULLONG_MAX - latency) {
                current_sum_latency += latency;
                s_avg_latency =
                    static_cast<double>(current_sum_latency) / num_reads_issued;
              } else {
                DEBUG_PRINT("Overflow detected in latency sum calculation");
              }
              if (latency > s_max_read_latency)
                s_max_read_latency = latency; // update maximum latency
            }
          }
        }

        if (req.callback) {
          // If the request comes from outside (e.g., processor), call its
          // callback
          req.callback(req);
        }
        if (req.mitigation_type == Request::MitigationType::RD) {
          remove_one_metadata_proq_entry(req);
        }
        // Finally, remove this request from the pending queue
        pending.pop_front();
      }
    };
  };

  bool contains_drfm() {
    for (Request &item : m_read_buffer) {
      if (item.type_id == Request::Type::DRFMsb) {
        return true;
      }
    }
    return false;
  }

  bool pro_targets_address(const Request &req, const AddrVec_t &addr) {
    if (req.type_id != m_dram->m_requests("same-bank-directed-rfm") &&
        req.type_id != m_dram->m_requests("directed-rfm")) {
      return false;
    }

    for (size_t i = 0; i < addr.size(); i++) {
      // -1 is a wildcard (e.g., bank group for DRFMsb and bank for DRFMab).
      if (req.addr_vec[i] != -1 && addr[i] != -1 &&
          req.addr_vec[i] != addr[i]) {
        return false;
      }
    }
    return true;
  }

  void prioritize_proq_for_occupancy() {
    if (m_occupancy_promoted_request_pending ||
        blacklist.size() < m_proq_occupancy_promotion_threshold) {
      return;
    }

    bool from_tail = m_drain_proq_from_tail &&
                     blacklist.size() > m_proq_occupancy_promotion_threshold;
    const TrackedPROQEntry target =
        from_tail ? blacklist.back() : blacklist.front();
    ReqBuffer& source_buffer = target.type == Request::MitigationType::WR
                                   ? m_write_buffer
                                   : m_read_buffer;
    for (auto it = source_buffer.begin(); it != source_buffer.end(); ++it) {
      if (request_matches_entry(*it, target)) {
        // This request was already accepted and counted when it entered the
        // controller, so move it directly rather than calling priority_send().
        if (!m_priority_buffer.enqueue(*it)) {
          return;
        }
        m_occupancy_promoted_addr = it->addr_vec;
        m_occupancy_promoted_type = it->mitigation_type;
        m_occupancy_promoted_from_tail = from_tail;
        m_occupancy_promoted_request_pending = true;
        if (target.type == Request::MitigationType::RD) {
          s_num_capacity_promotions_rd++;
        } else if (target.type == Request::MitigationType::WR) {
          s_num_capacity_promotions_wr++;
        } else if (target.type == Request::MitigationType::PRO) {
          s_num_capacity_promotions_pro++;
        }
        source_buffer.remove(it);
        return;
      }
    }
  }

  /**
   * @brief    Checks if we need to switch to write mode
   *
   */
  void set_write_mode() {
    if (!m_is_write_mode) {
      if ((blacklist.size() >= 10 && contains_drfm()) || not_found_req > 30) {
        not_found_req = 0;
        return;
      }
      if ((m_write_buffer.size() >
           m_wr_high_watermark * m_write_buffer.max_size) ||
          m_read_buffer.size() == 0) {
        m_is_write_mode = true;
        DEBUG_PRINT("WRITE MODE");
      }
    } else {
      // Avoid draining writes while mitigations are blocking reads.
      if ((blacklist.size() >= 10 && contains_drfm()) || not_found_req > 30) {
        not_found_req = 0;
        m_is_write_mode = false;
        DEBUG_PRINT("READ MODE");
      }
      if ((m_write_buffer.size() <
           m_wr_low_watermark * m_write_buffer.max_size) &&
          m_read_buffer.size() != 0) {
        m_is_write_mode = false;
        DEBUG_PRINT("READ MODE");
      }
    }
  };

  int get_num_ready_demand_requests(ReqBuffer &buffer) {
    int count = 0;
    for (auto it = buffer.begin(); it != buffer.end(); ++it) {
      // Figure 13 measures processor demand only. Hydra and other mechanisms
      // may place metadata RD/WR requests in these same buffers.
      if (it->mitigation_type != Request::MitigationType::None) {
        continue;
      }
      // Refresh the prerequisite before testing readiness: when a PRO comes
      // from the priority buffer, the read/write buffers may not have been
      // visited by the scheduler in this cycle.
      const int command =
          m_dram->get_preq_command(it->final_command, it->addr_vec);
      if ((command == m_dram->m_commands("RD") ||
           command == m_dram->m_commands("WR")) &&
          m_dram->check_ready(command, it->addr_vec)) {
        count++;
      }
    }
    return count;
  }

  void record_demand_requests_delayed_by_PRO() {
    const int reads_waiting = get_num_ready_demand_requests(m_read_buffer);
    const int writes_waiting = get_num_ready_demand_requests(m_write_buffer);

    read_demand_delayed_by_PRO += reads_waiting;
    write_demand_delayed_by_PRO += writes_waiting;
    demand_delayed_by_PRO += reads_waiting + writes_waiting;

    max_num_read_demand_delayed_by_PRO =
        std::max(max_num_read_demand_delayed_by_PRO, reads_waiting);
    max_num_write_demand_delayed_by_PRO =
        std::max(max_num_write_demand_delayed_by_PRO, writes_waiting);
    max_num_demand_delayed_by_PRO = std::max(
        max_num_demand_delayed_by_PRO, reads_waiting + writes_waiting);
    num_counted_PROs += 1;

    DEBUG_PRINT("PRO is issued, reads waiting: " << reads_waiting
        << ", writes waiting: " << writes_waiting);
  }

  /**
   * @brief    Helper function to find a request to schedule from the buffers.
   *
   */
  bool schedule_request(ReqBuffer::iterator &req_it, ReqBuffer *&req_buffer) {
    bool request_found = false;
    // 2.1    First, check the act buffer to serve requests that are already
    // activating (avoid useless ACTs)
    req_it = m_scheduler->get_best_request(m_active_buffer);
    if (req_it != m_active_buffer.end()) {
      // no need to check if blacklisted, because goes to an open row
      if (m_dram->check_ready(req_it->command, req_it->addr_vec)) {
        request_found = true;
        DEBUG_PRINT("request found in active buffer");

        req_buffer = &m_active_buffer;
      }
    }

    // 2.2    If no requests can be scheduled from the act buffer, check the
    // rest of the buffers
    if (!request_found) {
      // 2.2.1    We first check the priority buffer to prioritize e.g.,
      // maintenance requests
      if (m_priority_buffer.size() != 0) {
        req_buffer = &m_priority_buffer;

        req_it = m_scheduler->get_best_request(m_priority_buffer);

        req_it->command =
            m_dram->get_preq_command(req_it->final_command, req_it->addr_vec);

        // check that ready
        request_found = m_dram->check_ready(req_it->command, req_it->addr_vec);
        if (request_found) {
            DEBUG_PRINT("request found in priority queue, queue length "
                << m_priority_buffer.size());

            // check that request is a PRO
            if ((req_it->type_id == m_dram->m_requests("same-bank-directed-rfm" )
                  && req_it->command == m_dram->m_commands("DRFMsb")) ||
                (req_it->type_id == m_dram->m_requests("directed-rfm")
                  && req_it->command == m_dram->m_commands("DRFMab"))) {
              record_demand_requests_delayed_by_PRO();
            }

          }

        if (!request_found & (m_priority_buffer.size() != 0)) {
          return false;
        }
      }

      // 2.2.1    If no request to be scheduled in the priority buffer, check
      // the read and write buffers.
      if (!request_found) {
        // Query the write policy to decide which buffer to serve

        set_write_mode();

        auto &buffer = m_is_write_mode ? m_write_buffer : m_read_buffer;
        req_it = m_scheduler->get_best_request(buffer);

        if (req_it != buffer.end()) {
          // check that ready and not blacklisted
          request_found =
            (m_dram->check_ready(req_it->command, req_it->addr_vec) &&
            (!checkBlacklisted(*req_it) ||
            req_it->type_id == m_dram->m_requests("same-bank-directed-rfm") ||
            req_it->type_id == m_dram->m_requests("directed-rfm") ||
            is_to_open_row(req_it)));
          if (request_found) {
            //count request that are delayed by PRO if we are issueing a PRO:
            if ((req_it->type_id == m_dram->m_requests("same-bank-directed-rfm" )
                  && req_it->command == m_dram->m_commands("DRFMsb")) ||
                (req_it->type_id == m_dram->m_requests("directed-rfm")
                  && req_it->command == m_dram->m_commands("DRFMab"))) {
              record_demand_requests_delayed_by_PRO();
            }
          }
          req_buffer = &buffer;
        }
      }
    }

    // 2.3 If we find a request to schedule, we need to check if it will close
    // an opened row in the active buffer.
    if (request_found) {
      if (m_dram->m_command_meta(req_it->command).is_closing) {
        auto &rowgroup = req_it->addr_vec;
        for (auto _it = m_active_buffer.begin(); _it != m_active_buffer.end();
             _it++) {
          auto &_it_rowgroup = _it->addr_vec;
          bool is_matching = true;
          for (int i = 0; i < m_bank_addr_idx + 1; i++) {
            if (_it_rowgroup[i] != rowgroup[i] && _it_rowgroup[i] != -1 &&
                rowgroup[i] != -1) {
              is_matching = false;
              break;
            }
          }
          if (is_matching) {
            request_found = false;
            DEBUG_PRINT("is matching");
            break;
          }
        }
      }
    }
    if (!request_found) {
      // keep track of the fact that we have not found a request
      not_found_req += 1;
    } else {
      // we have found a request, reset the counter
      not_found_req = 0;
    }
    return request_found;
  }

  void finalize() override {
    s_avg_read_latency = (float)s_read_latency / (float)s_num_read_reqs;
    s_avg_proq_time = s_total_proq_time / s_num_proq_remv;

    s_queue_len_avg = (float)s_queue_len / (float)m_clk;
    s_read_queue_len_avg = (float)s_read_queue_len / (float)m_clk;
    s_write_queue_len_avg = (float)s_write_queue_len / (float)m_clk;
    s_priority_queue_len_avg = (float)s_priority_queue_len / (float)m_clk;
    s_avg_blacklist_size = (float)s_blacklist_len / (float)m_clk;
    avg_num_demand_delayed_by_PRO =
        num_counted_PROs == 0
            ? 0.0F
            : static_cast<float>(demand_delayed_by_PRO) /
                  static_cast<float>(num_counted_PROs);
    avg_num_read_demand_delayed_by_PRO =
        num_counted_PROs == 0
            ? 0.0F
            : static_cast<float>(read_demand_delayed_by_PRO) /
                  static_cast<float>(num_counted_PROs);
    avg_num_write_demand_delayed_by_PRO =
        num_counted_PROs == 0
            ? 0.0F
            : static_cast<float>(write_demand_delayed_by_PRO) /
                  static_cast<float>(num_counted_PROs);
    return;
  }
};

} // namespace Ramulator
