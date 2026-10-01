% ==============================================================================
% NetVerity: Network Fault Diagnosis Knowledge Base & Rules
% ==============================================================================

:- dynamic fact/2.

% ------------------------------------------------------------------------------
% 1. Core Diagnostic Fault Rules (MVP + Extended)
% ------------------------------------------------------------------------------

% Wi-Fi Authentication / Association Failure
% Wi-Fi connection is not established.
possible_fault(wifi_auth_failure) :-
    fact(wifi_connected, false).

% DHCP Failure
% Connected to physical/Wi-Fi media, but failed to obtain a valid IP address.
possible_fault(dhcp_failure) :-
    fact(wifi_connected, true),
    fact(has_valid_ip, false).

% Default Gateway Failure
% Has a valid IP address, but cannot reach the local default gateway.
possible_fault(gateway_failure) :-
    fact(has_valid_ip, true),
    fact(gateway_reachable, false).

% DNS Resolution Failure
% IP, Gateway, and Public Internet IP are all reachable, but domain name lookup fails.
possible_fault(dns_failure) :-
    fact(has_valid_ip, true),
    fact(gateway_reachable, true),
    fact(internet_ip_reachable, true),
    fact(dns_resolution_ok, false).

% WAN / Upstream ISP Connectivity Failure
% Gateway is reachable locally, but routing/pinging to public IP fails.
possible_fault(wan_failure) :-
    fact(has_valid_ip, true),
    fact(gateway_reachable, true),
    fact(internet_ip_reachable, false).

% Packet Loss / Intermittent Link Degradation
possible_fault(packet_loss_failure) :-
    fact(has_valid_ip, true),
    fact(gateway_reachable, true),
    fact(packet_loss_high, true).

% Firewall Blocking Traffic
possible_fault(firewall_blocking) :-
    fact(has_valid_ip, true),
    fact(gateway_reachable, true),
    fact(firewall_blocking_traffic, true).

% IP Address Conflict
possible_fault(ip_conflict) :-
    fact(ip_conflict_detected, true).

% Proxy Configuration Problem
possible_fault(proxy_failure) :-
    fact(internet_ip_reachable, true),
    fact(proxy_enabled, true),
    fact(proxy_reachable, false).

% Ethernet Link Down
possible_fault(ethernet_link_down) :-
    fact(ethernet_connected, false).


% ------------------------------------------------------------------------------
% 2. Topological & Domain Contradiction Constraints
% ------------------------------------------------------------------------------

% It is logically impossible to reach public IP if local default gateway is unreachable.
domain_contradiction(internet_without_gateway) :-
    fact(gateway_reachable, false),
    fact(internet_ip_reachable, true).

% It is impossible to resolve DNS over public servers if public IP is unreachable and gateway is down.
domain_contradiction(dns_without_ip) :-
    fact(has_valid_ip, false),
    fact(dns_resolution_ok, true).

% Disconnected from Wi-Fi yet claiming valid local Wi-Fi IP address
domain_contradiction(ip_without_link) :-
    fact(wifi_connected, false),
    fact(ethernet_connected, false),
    fact(has_valid_ip, true).


% ------------------------------------------------------------------------------
% 3. Diagnostic Queries & Evaluation Entry Points
% ------------------------------------------------------------------------------

all_supported_faults(Faults) :-
    findall(F, possible_fault(F), Faults).

all_contradictions(Contradictions) :-
    findall(C, domain_contradiction(C), Contradictions).
