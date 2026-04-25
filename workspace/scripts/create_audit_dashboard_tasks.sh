#!/bin/bash
set -e

NOTION_KEY=$(cat ~/.config/notion/api_key 2>/dev/null || echo $NOTION_API_KEY)
DB_ID="4494fedd-faee-47d7-a475-595e3c18370a"
SANDEEP_ID="333d872b-594c-813a-bf0a-0002e1a1dc22"
HEADERS=(-H "Authorization: Bearer $NOTION_KEY" -H "Notion-Version: 2025-09-03" -H "Content-Type: application/json")

create_page() {
  local payload="$1"
  local result
  result=$(curl -s -X POST "https://api.notion.com/v1/pages" "${HEADERS[@]}" -d "$payload")
  local page_id=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id','ERROR'))" 2>/dev/null)
  if [ "$page_id" = "ERROR" ] || [ -z "$page_id" ]; then
    echo "ERROR: $result" >&2
    echo "ERROR"
  else
    echo "$page_id"
  fi
  sleep 0.4
}

echo "=== Creating Epic Story: Audit Dashboard Bug Fixing & Improvements ==="

EPIC_ID=$(create_page '{
  "parent": {"database_id": "'$DB_ID'"},
  "properties": {
    "Task Name": {"title": [{"text": {"content": "Audit Dashboard Bug Fixing & Improvements"}}]},
    "Type": {"select": {"name": "Task"}},
    "Status": {"select": {"name": "Done"}},
    "Priority": {"select": {"name": "P0 Critical"}},
    "Owner": {"people": [{"id": "'$SANDEEP_ID'"}]},
    "Sprint": {"select": {"name": "Sprint 3"}},
    "Source": {"select": {"name": "manual"}},
    "Notes": {"rich_text": [{"text": {"content": "Epic: Chat Analytics Dashboard v2. 5 stories + 4 bug fixes. Server-side search/pagination, analytics cache, overview API, interactive Plotly charts, tab navigation. All code done, pending production deploy."}}]}
  }
}')
echo "Epic ID: $EPIC_ID"

echo "=== Story 1: Search & Server-Side Pagination (P0, 1d, Done) ==="
S1_ID=$(create_page '{
  "parent": {"database_id": "'$DB_ID'"},
  "properties": {
    "Task Name": {"title": [{"text": {"content": "Search & Server-Side Pagination"}}]},
    "Type": {"select": {"name": "Task"}},
    "Status": {"select": {"name": "Done"}},
    "Priority": {"select": {"name": "P0 Critical"}},
    "Effort": {"select": {"name": "M"}},
    "Owner": {"people": [{"id": "'$SANDEEP_ID'"}]},
    "Sprint": {"select": {"name": "Sprint 3"}},
    "Source": {"select": {"name": "manual"}},
    "Parent": {"relation": [{"id": "'$EPIC_ID'"}]},
    "Notes": {"rich_text": [{"text": {"content": "Chunk 1/5. Server-side search by name/user ID, pagination via /chat-threads/by-user endpoint. Repos: BonCredGPT + BON-Dashboard."}}]},
    "Acceptance Criteria": {"rich_text": [{"text": {"content": "Search by user ID or name works. /chat-threads/by-user returns paginated results. Dashboard scales past 500+ threads. Existing API calls unchanged."}}]}
  }
}')
echo "Story 1 ID: $S1_ID"

# Story 1 sub-tasks
for task_json in \
  '{"name":"Add search param to GET /chat-threads","notes":"BonCredGPT src/server/main.py. Optional search query param, SQL match against LOWER(first_name), LOWER(last_name), or exact user_id."}' \
  '{"name":"Raise admin limit cap to 1000","notes":"BonCredGPT src/server/main.py. Admin callers can pass limit=1000. Dashboard uses limit=500."}' \
  '{"name":"New endpoint GET /chat-threads/by-user","notes":"BonCredGPT src/server/main.py. Admin-authed, aggregated users with thread counts, server-side pagination, search/date filters."}' \
  '{"name":"Refactor dashboard get_chat_threads() service","notes":"BON-Dashboard app/services/chat_analytics_service.py. Replace client-side aggregation with /chat-threads/by-user API call. Delete ~40 lines."}' \
  '{"name":"Template tweaks for pagination","notes":"BON-Dashboard app/templates/chat_analytics/list.html. Pagination links preserve name and activity params."}'; do
  
  tname=$(echo "$task_json" | python3 -c "import json,sys; print(json.load(sys.stdin)['name'])")
  tnotes=$(echo "$task_json" | python3 -c "import json,sys; print(json.load(sys.stdin)['notes'])")
  
  create_page '{
    "parent": {"database_id": "'$DB_ID'"},
    "properties": {
      "Task Name": {"title": [{"text": {"content": "'"$tname"'"}}]},
      "Type": {"select": {"name": "Sub-task"}},
      "Status": {"select": {"name": "Done"}},
      "Priority": {"select": {"name": "P0 Critical"}},
      "Effort": {"select": {"name": "S"}},
      "Owner": {"people": [{"id": "'$SANDEEP_ID'"}]},
      "Sprint": {"select": {"name": "Sprint 3"}},
      "Parent": {"relation": [{"id": "'$S1_ID'"}]},
      "Notes": {"rich_text": [{"text": {"content": "'"$tnotes"'"}}]}
    }
  }' > /dev/null
  echo "  Sub-task: $tname ✓"
done

echo "=== Story 2: Analytics Cache Foundation (P0, 1d, Done) ==="
S2_ID=$(create_page '{
  "parent": {"database_id": "'$DB_ID'"},
  "properties": {
    "Task Name": {"title": [{"text": {"content": "Analytics Cache Foundation"}}]},
    "Type": {"select": {"name": "Task"}},
    "Status": {"select": {"name": "Done"}},
    "Priority": {"select": {"name": "P0 Critical"}},
    "Effort": {"select": {"name": "M"}},
    "Owner": {"people": [{"id": "'$SANDEEP_ID'"}]},
    "Sprint": {"select": {"name": "Sprint 3"}},
    "Source": {"select": {"name": "manual"}},
    "Parent": {"relation": [{"id": "'$EPIC_ID'"}]},
    "Notes": {"rich_text": [{"text": {"content": "Chunk 2/5. Denormalized chat_analytics_cache table with fire-and-forget write hook and historical backfill script. Repo: BonCredGPT."}}]},
    "Acceptance Criteria": {"rich_text": [{"text": {"content": "Table exists after startup. New chat turns populate cache within ~2s. Write failures dont break chat flow. Backfill script runs end-to-end, idempotent."}}]}
  }
}')
echo "Story 2 ID: $S2_ID"

for task_json in \
  '{"name":"Create chat_analytics_cache table (idempotent startup DDL)","notes":"BonCredGPT src/server/main.py. Columns: thread_id, user_id, turn, question, intent, agent, suggestions (JSONB), latency_ms, created_at, cached_at. PK: (thread_id, turn). Indexes on user_id, intent, agent, created_at."}' \
  '{"name":"Fire-and-forget write hook","notes":"BonCredGPT src/server/main.py. _cache_turn_analytics_safe() wraps inner logic in try/except. Called via asyncio.create_task(). UPSERT with ON CONFLICT. Never blocks chat response."}' \
  '{"name":"Historical backfill script","notes":"BonCredGPT scripts/backfill_chat_analytics_cache.py (new). Reads all threads, extracts turns, UPSERTs with bounded concurrency. CLI flags: --concurrency, --batch-size, --thread-id, --since. Idempotent."}'; do
  
  tname=$(echo "$task_json" | python3 -c "import json,sys; print(json.load(sys.stdin)['name'])")
  tnotes=$(echo "$task_json" | python3 -c "import json,sys; print(json.load(sys.stdin)['notes'])")
  
  create_page '{
    "parent": {"database_id": "'$DB_ID'"},
    "properties": {
      "Task Name": {"title": [{"text": {"content": "'"$tname"'"}}]},
      "Type": {"select": {"name": "Sub-task"}},
      "Status": {"select": {"name": "Done"}},
      "Priority": {"select": {"name": "P0 Critical"}},
      "Effort": {"select": {"name": "S"}},
      "Owner": {"people": [{"id": "'$SANDEEP_ID'"}]},
      "Sprint": {"select": {"name": "Sprint 3"}},
      "Parent": {"relation": [{"id": "'$S2_ID'"}]},
      "Notes": {"rich_text": [{"text": {"content": "'"$tnotes"'"}}]}
    }
  }' > /dev/null
  echo "  Sub-task: $tname ✓"
done

echo "=== Story 3: Overview API Endpoint (P0, 0.5d, Done) ==="
S3_ID=$(create_page '{
  "parent": {"database_id": "'$DB_ID'"},
  "properties": {
    "Task Name": {"title": [{"text": {"content": "Overview API Endpoint"}}]},
    "Type": {"select": {"name": "Task"}},
    "Status": {"select": {"name": "Done"}},
    "Priority": {"select": {"name": "P0 Critical"}},
    "Effort": {"select": {"name": "S"}},
    "Owner": {"people": [{"id": "'$SANDEEP_ID'"}]},
    "Sprint": {"select": {"name": "Sprint 3"}},
    "Source": {"select": {"name": "manual"}},
    "Parent": {"relation": [{"id": "'$EPIC_ID'"}]},
    "Notes": {"rich_text": [{"text": {"content": "Chunk 3/5. GET /api/chat-analytics/overview — single admin-authed endpoint returning summary stats, daily activity, top-N lists via 7 parallel SQL queries. Repo: BonCredGPT."}}]},
    "Acceptance Criteria": {"rich_text": [{"text": {"content": "days=7/30/90/0 all work. search scopes all stats. Empty cache returns zeros. Thread counts match Users tab. Response < 1s on dev."}}]}
  }
}')
echo "Story 3 ID: $S3_ID"

for task_json in \
  '{"name":"GET /api/chat-analytics/overview endpoint","notes":"BonCredGPT src/server/main.py. Admin-authed, params: days (default 30), top_n (default 10), search. 7 parallel SQL queries via asyncio.gather(): summary stats, daily activity, top users/intents/agents/questions/suggestions."}' \
  '{"name":"Data consistency fix: thread counts from chat_threads","notes":"BonCredGPT src/server/main.py. Summary total_threads/threads_today/total_users/active_today query chat_threads (authoritative) instead of cache. Fixes count mismatch."}'; do
  
  tname=$(echo "$task_json" | python3 -c "import json,sys; print(json.load(sys.stdin)['name'])")
  tnotes=$(echo "$task_json" | python3 -c "import json,sys; print(json.load(sys.stdin)['notes'])")
  
  create_page '{
    "parent": {"database_id": "'$DB_ID'"},
    "properties": {
      "Task Name": {"title": [{"text": {"content": "'"$tname"'"}}]},
      "Type": {"select": {"name": "Sub-task"}},
      "Status": {"select": {"name": "Done"}},
      "Priority": {"select": {"name": "P0 Critical"}},
      "Effort": {"select": {"name": "S"}},
      "Owner": {"people": [{"id": "'$SANDEEP_ID'"}]},
      "Sprint": {"select": {"name": "Sprint 3"}},
      "Parent": {"relation": [{"id": "'$S3_ID'"}]},
      "Notes": {"rich_text": [{"text": {"content": "'"$tnotes"'"}}]}
    }
  }' > /dev/null
  echo "  Sub-task: $tname ✓"
done

echo "=== Story 4: Overview Dashboard UI (P1, 1.5d, Done) ==="
S4_ID=$(create_page '{
  "parent": {"database_id": "'$DB_ID'"},
  "properties": {
    "Task Name": {"title": [{"text": {"content": "Overview Dashboard UI"}}]},
    "Type": {"select": {"name": "Task"}},
    "Status": {"select": {"name": "Done"}},
    "Priority": {"select": {"name": "P1 High"}},
    "Effort": {"select": {"name": "L"}},
    "Owner": {"people": [{"id": "'$SANDEEP_ID'"}]},
    "Sprint": {"select": {"name": "Sprint 3"}},
    "Source": {"select": {"name": "manual"}},
    "Parent": {"relation": [{"id": "'$EPIC_ID'"}]},
    "Notes": {"rich_text": [{"text": {"content": "Chunk 4/5. Interactive overview page with summary cards, Plotly charts (daily activity, top intents/agents), top users/questions tables, custom searchable dropdown. Repo: BON-Dashboard."}}]},
    "Acceptance Criteria": {"rich_text": [{"text": {"content": "Overview renders with no errors. 6 summary cards populated. Charts render correctly. Period selector works. User search scopes all stats. Empty state graceful."}}]}
  }
}')
echo "Story 4 ID: $S4_ID"

for task_json in \
  '{"name":"Overview service function","notes":"BON-Dashboard app/services/chat_analytics_service.py. get_chat_overview(), get_all_chat_users(), _normalize_overview_search(). Error handling with empty fallback."}' \
  '{"name":"Overview route handler","notes":"BON-Dashboard app/routers/chat_analytics.py. GET /overview route with days, top_n, search params. Parallel fetch via asyncio.gather(). Auth check."}' \
  '{"name":"Overview template with Plotly charts","notes":"BON-Dashboard app/templates/chat_analytics/overview.html (new). Summary cards, daily activity bar chart, top users/intents/agents/questions/suggestions. Dark theme, responsive CSS grid. Period filter: 7d/15d/30d/90d/All time."}' \
  '{"name":"Custom searchable user dropdown (Overview)","notes":"BON-Dashboard overview.html. Custom JS dropdown replacing native datalist. Shows all users on focus, live filtering, keyboard navigation, hidden input sync, dark theme."}' \
  '{"name":"Admin API key config","notes":"BON-Dashboard app/config.py. Added admin_api_key field to Settings (reads ADMIN_API_KEY env var). Used by _admin_headers() in service layer."}'; do
  
  tname=$(echo "$task_json" | python3 -c "import json,sys; print(json.load(sys.stdin)['name'])")
  tnotes=$(echo "$task_json" | python3 -c "import json,sys; print(json.load(sys.stdin)['notes'])")
  
  create_page '{
    "parent": {"database_id": "'$DB_ID'"},
    "properties": {
      "Task Name": {"title": [{"text": {"content": "'"$tname"'"}}]},
      "Type": {"select": {"name": "Sub-task"}},
      "Status": {"select": {"name": "Done"}},
      "Priority": {"select": {"name": "P1 High"}},
      "Effort": {"select": {"name": "S"}},
      "Owner": {"people": [{"id": "'$SANDEEP_ID'"}]},
      "Sprint": {"select": {"name": "Sprint 3"}},
      "Parent": {"relation": [{"id": "'$S4_ID'"}]},
      "Notes": {"rich_text": [{"text": {"content": "'"$tnotes"'"}}]}
    }
  }' > /dev/null
  echo "  Sub-task: $tname ✓"
done

echo "=== Story 5: Navigation, Tabs & UX Polish (P1, 0.5d, Done) ==="
S5_ID=$(create_page '{
  "parent": {"database_id": "'$DB_ID'"},
  "properties": {
    "Task Name": {"title": [{"text": {"content": "Navigation, Tabs & UX Polish"}}]},
    "Type": {"select": {"name": "Task"}},
    "Status": {"select": {"name": "Done"}},
    "Priority": {"select": {"name": "P1 High"}},
    "Effort": {"select": {"name": "S"}},
    "Owner": {"people": [{"id": "'$SANDEEP_ID'"}]},
    "Sprint": {"select": {"name": "Sprint 3"}},
    "Source": {"select": {"name": "manual"}},
    "Parent": {"relation": [{"id": "'$EPIC_ID'"}]},
    "Notes": {"rich_text": [{"text": {"content": "Chunk 5/5. Tab navigation between Overview and Users, sidebar/hub link updates, searchable dropdown on Users tab, Created+Last Active dates on thread cards, activity period filters. Repo: BON-Dashboard."}}]},
    "Acceptance Criteria": {"rich_text": [{"text": {"content": "Tab bar on both pages with correct active state. Sidebar lands on overview. Both dates shown on thread cards. Searchable dropdown on both tabs. Activity filter works."}}]}
  }
}')
echo "Story 5 ID: $S5_ID"

for task_json in \
  '{"name":"Sub-nav tab bar on both pages","notes":"BON-Dashboard list.html + overview.html. Overview and Users tabs, active highlighted with cyan border, active_tab variable from route handlers."}' \
  '{"name":"Sidebar link update","notes":"BON-Dashboard app/templates/base.html. Chat Analytics link now points to /dashboard/chat-analytics/overview. Old URL still works."}' \
  '{"name":"Hub page link update","notes":"BON-Dashboard app/templates/home.html. Chat Analytics card links to overview page."}' \
  '{"name":"Custom searchable user dropdown (Users tab)","notes":"BON-Dashboard list.html. Same custom JS dropdown as overview. Live filter by name or user ID, keyboard nav, dark theme."}' \
  '{"name":"Show both Created & Last Active dates on thread cards","notes":"BON-Dashboard list.html (side panel) + conversation.html (sidebar). Fixes date mismatch. Invalidated stale sessionStorage with v2 cache key."}' \
  '{"name":"Activity period filters on Users tab","notes":"BON-Dashboard list.html. Dropdown: Last 1d/3d/7d/All time. Auto-submits, filters by updated_after."}'; do
  
  tname=$(echo "$task_json" | python3 -c "import json,sys; print(json.load(sys.stdin)['name'])")
  tnotes=$(echo "$task_json" | python3 -c "import json,sys; print(json.load(sys.stdin)['notes'])")
  
  create_page '{
    "parent": {"database_id": "'$DB_ID'"},
    "properties": {
      "Task Name": {"title": [{"text": {"content": "'"$tname"'"}}]},
      "Type": {"select": {"name": "Sub-task"}},
      "Status": {"select": {"name": "Done"}},
      "Priority": {"select": {"name": "P1 High"}},
      "Effort": {"select": {"name": "S"}},
      "Owner": {"people": [{"id": "'$SANDEEP_ID'"}]},
      "Sprint": {"select": {"name": "Sprint 3"}},
      "Parent": {"relation": [{"id": "'$S5_ID'"}]},
      "Notes": {"rich_text": [{"text": {"content": "'"$tnotes"'"}}]}
    }
  }' > /dev/null
  echo "  Sub-task: $tname ✓"
done

echo "=== Bug Fixes ==="

echo "--- Bug Fix 1: Thread Count Mismatch (P0, Fixed) ---"
create_page '{
  "parent": {"database_id": "'$DB_ID'"},
  "properties": {
    "Task Name": {"title": [{"text": {"content": "Bug Fix: Thread Count Mismatch Between Overview & Users Tab"}}]},
    "Type": {"select": {"name": "Task"}},
    "Status": {"select": {"name": "Done"}},
    "Priority": {"select": {"name": "P0 Critical"}},
    "Effort": {"select": {"name": "S"}},
    "Owner": {"people": [{"id": "'$SANDEEP_ID'"}]},
    "Sprint": {"select": {"name": "Sprint 3"}},
    "Source": {"select": {"name": "bug"}},
    "Parent": {"relation": [{"id": "'$EPIC_ID'"}]},
    "Notes": {"rich_text": [{"text": {"content": "Root cause: Overview counted threads from chat_analytics_cache (missing uncached threads). Fix: _overview_summary and _overview_top_users now query chat_threads table. Impact: User 1782 showed 3 vs 6 threads."}}]}
  }
}' > /dev/null
echo "  Bug Fix 1 ✓"

echo "--- Bug Fix 2: Daily Activity Chart Missing Thread Dates (P1, Fixed) ---"
create_page '{
  "parent": {"database_id": "'$DB_ID'"},
  "properties": {
    "Task Name": {"title": [{"text": {"content": "Bug Fix: Daily Activity Chart Missing Thread Dates"}}]},
    "Type": {"select": {"name": "Task"}},
    "Status": {"select": {"name": "Done"}},
    "Priority": {"select": {"name": "P1 High"}},
    "Effort": {"select": {"name": "S"}},
    "Owner": {"people": [{"id": "'$SANDEEP_ID'"}]},
    "Sprint": {"select": {"name": "Sprint 3"}},
    "Source": {"select": {"name": "bug"}},
    "Parent": {"relation": [{"id": "'$EPIC_ID'"}]},
    "Notes": {"rich_text": [{"text": {"content": "Root cause: Side panel only showed updated_at, hiding original creation date. Fix: Show both Created and Last Active dates on thread cards."}}]}
  }
}' > /dev/null
echo "  Bug Fix 2 ✓"

echo "--- Bug Fix 3: Stale Session Cache After Deploy (P1, Fixed) ---"
create_page '{
  "parent": {"database_id": "'$DB_ID'"},
  "properties": {
    "Task Name": {"title": [{"text": {"content": "Bug Fix: Stale Session Cache After Deploy"}}]},
    "Type": {"select": {"name": "Task"}},
    "Status": {"select": {"name": "Done"}},
    "Priority": {"select": {"name": "P1 High"}},
    "Effort": {"select": {"name": "S"}},
    "Owner": {"people": [{"id": "'$SANDEEP_ID'"}]},
    "Sprint": {"select": {"name": "Sprint 3"}},
    "Source": {"select": {"name": "bug"}},
    "Parent": {"relation": [{"id": "'$EPIC_ID'"}]},
    "Notes": {"rich_text": [{"text": {"content": "Root cause: Browser sessionStorage cached old data without created_at field. Fix: Changed cache key to chat_threads_cache_v2 to invalidate stale entries."}}]}
  }
}' > /dev/null
echo "  Bug Fix 3 ✓"

echo "--- Bug Fix 4: Tooltip Background Invisible on Charts (P2, Fixed) ---"
create_page '{
  "parent": {"database_id": "'$DB_ID'"},
  "properties": {
    "Task Name": {"title": [{"text": {"content": "Bug Fix: Tooltip Background Invisible on Charts"}}]},
    "Type": {"select": {"name": "Task"}},
    "Status": {"select": {"name": "Done"}},
    "Priority": {"select": {"name": "P2 Medium"}},
    "Effort": {"select": {"name": "S"}},
    "Owner": {"people": [{"id": "'$SANDEEP_ID'"}]},
    "Sprint": {"select": {"name": "Sprint 3"}},
    "Source": {"select": {"name": "bug"}},
    "Parent": {"relation": [{"id": "'$EPIC_ID'"}]},
    "Notes": {"rich_text": [{"text": {"content": "Root cause: Plotly tooltips used white background on dark theme — text invisible. Fix: Added DARK_HOVERLABEL config with #1e293b background and light text."}}]}
  }
}' > /dev/null
echo "  Bug Fix 4 ✓"

echo ""
echo "=== ALL DONE ==="
echo "Created:"
echo "  1 Epic (Audit Dashboard Bug Fixing & Improvements)"
echo "  5 Stories (parent → Epic)"
echo "  21 Sub-tasks (parent → respective Stories)"
echo "  4 Bug Fixes (parent → Epic)"
echo "  Total: 31 items"
