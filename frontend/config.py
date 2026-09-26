"""Frontend-only navigation, team responsibilities, and supplied profile links."""

TEAM_LINKEDIN = {
    "Jawaher": "https://www.linkedin.com/in/jawaher-khalifah-4277242a0",
    "Ghala": "https://www.linkedin.com/in/ghala-bander-alsuna-allah",
    "Hanan": "https://www.linkedin.com/in/hannansulaiman",
    "Hajer": "https://www.linkedin.com/in/hajeralsaleh",
}

TEAM = [
    {
        "name": "Jawaher",
        "verb": "Observe",
        "role": "Data + Monitoring",
        "stage": "01",
        "avatar": "observer",
        "accent": "cyan",
        "icon": "chart",
        "keywords": "Observe · Understand · Improve",
        "description": "Builds the data and monitoring layer that makes retrieval quality observable.",
    },
    {
        "name": "Ghala",
        "verb": "Diagnose",
        "role": "Evaluation + Diagnosis",
        "stage": "02",
        "avatar": "diagnostician",
        "accent": "teal",
        "icon": "search",
        "keywords": "Evaluate · Diagnose · Solve",
        "description": "Evaluates retrieval behavior and diagnoses the root cause of failures.",
    },
    {
        "name": "Hanan",
        "verb": "Optimize",
        "role": "Models + Optimization",
        "stage": "03",
        "avatar": "optimizer",
        "accent": "violet",
        "icon": "settings",
        "keywords": "Build · Optimize · Scale",
        "description": "Designs targeted model and retrieval optimizations.",
    },
    {
        "name": "Hajer",
        "verb": "Verify & Integrate",
        "role": "Validation + Integration + Frontend",
        "stage": "04",
        "avatar": "integrator",
        "accent": "amber",
        "icon": "layers",
        "keywords": "Validate · Integrate · Deliver",
        "description": "Validates impact and connects the workflow into the end-to-end product experience.",
    },
]

NAV_ITEMS = [
    ("overview", "Overview"),
    ("action", "RAGOps in Action"),
    ("dashboard", "Dashboard"),
    ("architecture", "Architecture"),
    ("team", "Team"),
]
