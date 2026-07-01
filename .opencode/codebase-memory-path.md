When using codebase-memory-mcp, never index the real OneDrive path.

Always use this repo_path:

C:/cbm/SentryBOTV5

If the user says "index this project", call codebase-memory-mcp_index_repository with:

repo_path: C:/cbm/SentryBOTV5
mode: full

Do not use:

C:\Users\emohi\OneDrive\Masaüstü\Project SentryBOT V5
