# Official Task 10 requirements checklist

Source inspected inside the workspace: `Elevvo Internship Tasks-20261019T182218Z-1-001.zip`, entry `Elevvo Internship Tasks/Natural Language Processing Tasks.pdf`, page 7. Checklist wording below follows that page.

## Core task

- [x] Dataset recommendation: “Chinook Database (Kaggle) or any mock E-commerce DB” — default setup downloads and verifies Chinook; user may also upload an existing SQLite database.
- [x] Challenge context: answer management questions such as “How much revenue did we make last Friday?” without waiting for an analyst to write code.
- [x] “Build an AI Agent (using LangChain or CrewAI) that translates natural language questions into executable SQL queries, runs them against the database, and summarizes the results.” — implemented as a bounded LangGraph state graph (LangChain ecosystem), OpenAI SQL generation, read-only execution, and result summarization.
- [x] “Implement Self-Correction Logic. If the agent writes invalid SQL that errors out, it must catch the error, read the error message, and rewrite the query automatically without crashing.” — recoverable syntax/schema errors can receive up to three correction attempts; all corrected SQL is revalidated.
- [x] Tools listed: LangChain/LangGraph, OpenAI/Gemini API, SQLite, Streamlit.
- [x] Covered topics listed: AI Agents, Function Calling, Text-to-SQL.

## Official bonus

- [x] “Add a \"Chart Tool\" so the agent can choose to generate a graph instead of text” — the SQL agent can return a chart suggestion; the app checks it against actual returned columns and only draws a supported chart from query results. Users can adjust its type and columns.
- [x] “Restrict the agent's permissions to Read-Only to ensure it cannot accidentally delete data” — SQLGlot policy validation, read-only SQLite URI, query-only mode, and a restrictive SQLite authorizer provide defense in depth.

## Additional enhancements from the supplied master prompt

The following are implemented as additional project features; they are not presented as wording from the official PDF: SQLite uploads, schema explorer, local history and favourites, CSV/SQL export, SQL explanation, benchmark harness, redacted logging, and schema-only mode without an API key.
