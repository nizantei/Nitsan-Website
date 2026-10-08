# DevMaster - Project Configuration

## What is DevMaster?

DevMaster is your local development dashboard. It gives you a single place to see all your projects, track progress, manage tasks, run scripts, and detect port conflicts — all from one UI at `http://localhost:4000`.

This `devmaster/` folder is how your project communicates with the dashboard. The JSON files inside control what appears on your project's page in DevMaster.

## How It Works

DevMaster reads 3 JSON files from this folder. Each file controls a different part of your project's dashboard page:

| File | Purpose | Dashboard Tab |
|------|---------|---------------|
| `devmaster_overview.json` | Identity, status, architecture, links, commands | **Overview** |
| `devmaster_tasks.json` | Milestones and tasks | **Tasks** + **Roadmap** |
| `devmaster_roadmap.json` | Vision statement, current phase | **Roadmap** header |

You don't need to fill everything at once. Start with `devmaster_overview.json` and add to the others as your project grows.

## Filling the Files

### devmaster_overview.json

This is the most important file. It defines your project's identity on the dashboard.

```jsonc
{
  "version": "1.0",
  "name": "My App",                    // Display name on dashboard
  "description": "What this app does", // One-liner shown under the name
  "status": "active",                  // active | paused | archived | idea | maintenance | completed
  "priority": "medium",               // critical | high | medium | low
  "tags": ["react", "mobile"],        // Free-form tags for filtering

  "ports": {
    "dev": [3000],                     // REQUIRED: Ports this app uses in development
    "custom": { "api": 3001 }          // Named ports (optional)
  },

  "commands": {
    "dev": "npm run dev",              // Standard commands
    "build": "npm run build",
    "test": "npm run test",
    "lint": "npm run lint"
  },

  "architecture": {
    "type": "nextjs",                  // Framework type
    "entry": "src/app/page.tsx",       // Main entry point
    "apiRoutes": "src/app/api/",       // Where API routes live
    "database": "PostgreSQL via Prisma", // DB tech
    "stateManagement": "Zustand",      // State management approach
    "styling": "Tailwind CSS",         // Styling solution
    "notes": "Any architectural notes" // Free text for important context
  },

  "links": [
    { "label": "GitHub", "url": "https://github.com/..." },
    { "label": "Figma", "url": "https://figma.com/..." },
    { "label": "Staging", "url": "https://staging.example.com" }
  ],

  "dashboard": {
    "pinned": false,                   // Pin to top of dashboard
    "group": "Client Work"             // Group label for organizing projects
  },

  "batFiles": {
    "seed": {                          // Key used internally
      "path": "scripts/seed-db.bat",   // Relative path to .bat file
      "label": "Seed Database",        // Display name in Tester
      "description": "Populates DB with test data" // Optional tooltip
    }
  }
}
```

**Required fields:** `name`, `description`, `ports.dev`
**Recommended:** `status`, `tags`, `commands`, `architecture.type`
**Everything else is optional** — add what's useful for your project.

### devmaster_tasks.json

Track your milestones and tasks. Each milestone groups related tasks together.

```jsonc
{
  "milestones": [
    {
      "id": "m1",                      // Unique ID (any string)
      "title": "MVP",
      "description": "Core features for first release",
      "targetDate": "2025-06-01",      // Optional target date
      "status": "in-progress",         // completed | in-progress | planned
      "tasks": [
        {
          "id": "t1",
          "title": "User authentication",
          "status": "done",            // done | in-progress | todo
          "category": "feature",       // feature | bugfix | refactor | devops | design | testing | docs
          "priority": "critical"       // critical | high | medium | low
        },
        {
          "id": "t2",
          "title": "Dashboard layout",
          "status": "in-progress",
          "category": "feature",
          "priority": "high"
        }
      ]
    }
  ],

  // Quick standalone tasks not tied to any milestone
  "currentTasks": [
    {
      "id": "ct1",
      "title": "Fix login redirect bug",
      "status": "todo",
      "category": "bugfix",
      "priority": "high"
    }
  ]
}
```

**Tips:**
- Use milestones for phases of work (MVP, V2, Launch, etc.)
- Use `currentTasks` for quick one-off items
- Update `status` as you work: `todo` -> `in-progress` -> `done`
- Task IDs just need to be unique within the file

### devmaster_roadmap.json

High-level vision and current phase. This appears at the top of the Roadmap tab.

```jsonc
{
  "vision": "Become the go-to analytics platform for small businesses",
  "currentPhase": "MVP"               // Should match a milestone title
}
```

Keep it simple — the detailed progress comes from your milestones in `devmaster_tasks.json`.

## Example Files

This folder includes `EXAMPLE_*.json` files showing a fully filled-out project. Use them as reference — don't edit them, they're just for guidance.

## For AI Assistants

If a developer asks you to "update the devmaster folder" or "fill in the devmaster config", here's what to do:

1. **Read the existing JSON files** in this folder to see what's already filled
2. **Analyze the project** — look at package.json, the src/ folder structure, any existing docs
3. **Fill in the fields** based on what you find:
   - `description`: Summarize what the app does in one sentence
   - `tags`: Extract from the tech stack and project purpose
   - `ports.dev`: REQUIRED - Check package.json scripts, .env files, or config for port numbers
   - `commands`: Pull from package.json scripts into the overview file
   - `architecture`: Describe the stack based on actual dependencies and folder structure
   - `milestones/tasks`: If the project has a TODO, issues, or roadmap, translate those
   - `links`: Check for git remote URLs, deployed URLs, documentation links
4. **Be descriptive but concise** — these fields appear on a dashboard UI
5. **Don't invent information** — only fill what you can verify from the codebase
6. **Preserve existing data** — merge new info with what's already there

The JSON files use standard JSON format (no comments in the actual files). The examples use `.json` extension.

## Keeping It Updated

As your project evolves:
- Update task statuses when you complete work
- Add new milestones when planning new phases
- Move `currentPhase` forward in the roadmap file
- Add new links as you set up staging, docs, etc.
- Update `architecture.notes` when you make significant technical decisions

This folder is yours — use it however helps you track your project.
