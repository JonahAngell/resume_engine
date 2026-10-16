STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "for", "in", "on", "with", "at", "by",
    "from", "as", "is", "are", "be", "was", "were", "been", "being", "our", "your",
    "you", "we", "they", "their", "this", "that", "these", "those", "it", "its",
    "will", "can", "may", "must", "should", "able", "ability", "experience",
    "experienced", "experiences", "years", "year", "team", "teams", "strong",
    "including", "include", "includes", "preferred", "required", "requirement",
    "requirements", "responsibilities", "responsibility", "qualifications",
    "qualification", "role", "job", "work", "working", "skills", "skill",
    "knowledge", "plus", "etc", "using", "use", "used", "across", "within", "into",
    "over", "about", "such", "other", "both", "all", "any", "not", "no", "well",
    "high", "looking", "seek", "seeking", "candidate", "candidates", "position",
    "positions", "opportunity", "company", "environment", "join", "apply",
    "application", "benefits", "equal", "employer", "related", "relevant",
    "minimum", "least", "more", "than", "per", "via", "who", "what", "when",
    "where", "which", "while", "also", "have", "has", "had", "having", "do",
    "does", "did", "done", "make", "makes", "making", "help", "helps", "need",
    "needs", "needed", "please", "based", "level", "levels", "senior", "junior",
    "staff", "proven", "demonstrated", "successful", "success", "excellent",
    "great", "good", "best", "new", "fast", "paced", "day", "today", "various",
    "multiple", "wide", "range", "hands",
}

ACRONYM_SKIP = {"US", "AM", "PM", "EOE", "TBD", "II", "III", "IV", "MS", "EST", "FL", "CA", "DX", "LLC", "FAQ", "POC", "POCS", "USD"}

DEGREE_LABELS = {
    1: "High school",
    2: "Associate degree",
    3: "Bachelor's degree",
    4: "Master's degree",
    5: "Doctorate",
}

LIST_ONLY = {"word": "Microsoft Word", "teams": "Microsoft Teams"}
BARE_TOOLS = {"microsoft word": "Word", "microsoft teams": "Teams"}
UMBRELLAS = {"microsoft office", "microsoft 365", "power platform", "microsoft suite"}
GENERIC_LIST = {
    "finance", "business", "technology", "management", "communication", "teams",
    "support", "skills", "experience", "knowledge", "global", "microsoft", "suite",
    "tools", "software", "systems", "applications", "reporting", "process",
    "project", "program", "data", "services", "operations", "partners",
    "stakeholders", "development", "environment", "technical", "professional",
    "senior", "analyst", "internal", "external", "multiple", "various", "other",
    "similar", "related", "equivalent", "system", "platform", "platforms",
}

GENERIC_WORDS = {
    "tools", "tool", "platforms", "platform", "language", "technologies",
    "technology", "software", "development", "methodology", "environments",
    "environment", "coding", "practices", "practice", "systems", "system",
    "particularly", "especially", "familiarity", "proficiency", "proficient",
    "preferably", "specifically", "following", "emerging", "query", "relevant",
}