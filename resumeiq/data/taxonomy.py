"""Skill taxonomy used for deterministic skill extraction, gap analysis and roadmaps.

Each skill: name, category, aliases, difficulty (1-3), est_hours (to job-ready
basics), prerequisites (skill names), topics (what to learn), description.
Aliases are matched case-insensitively on word boundaries unless listed in
`cs` (case-sensitive) or `rx` (raw regex).
"""

SKILLS = []


def S(name, category, aliases=(), d=2, h=25, pre=(), topics=(), desc="", cs=(), rx=None, soft=False):
    SKILLS.append({
        "name": name, "category": category, "aliases": list(aliases), "difficulty": d, "est_hours": h,
        "prerequisites": list(pre), "topics": list(topics), "description": desc,
        "case_sensitive_aliases": list(cs), "regex": rx, "is_soft": soft,
    })


# ── Programming languages ────────────────────────────────────────────────
S("Python", "language", ["python3", "python 3"], 1, 40, [],
  ["Syntax, data types and control flow", "Functions, modules and packages", "OOP and dataclasses",
   "Virtual environments and pip", "File I/O and error handling", "Standard library essentials"],
  "General-purpose language used for backend services, data and automation.")
S("Java", "language", ["java 8", "java 11", "java 17", "java 21", "core java"], 2, 60, [],
  ["Syntax, types and OOP", "Collections and generics", "Exceptions", "Streams and lambdas",
   "Build tools (Maven/Gradle)", "Concurrency basics"],
  "Statically typed JVM language widely used for enterprise backends and Android.")
S("JavaScript", "language", ["js", "es6", "ecmascript", "vanilla js"], 1, 45, ["HTML", "CSS"],
  ["Types, scope and closures", "DOM and events", "Promises and async/await", "Modules", "Fetch API"],
  "The language of the web, used in browsers and on servers via Node.js.")
S("TypeScript", "language", ["ts"], 2, 25, ["JavaScript"],
  ["Type annotations and inference", "Interfaces and generics", "Narrowing", "tsconfig and tooling"],
  "Typed superset of JavaScript for large codebases.")
S("C++", "language", ["cpp", "c plus plus"], 3, 80, [],
  ["Pointers and memory", "STL containers", "RAII and smart pointers", "Templates"],
  "Systems language used for performance-critical software.")
S("C", "language", [], 2, 50, [], ["Pointers", "Memory management", "Structs", "Compilation and linking"],
  "Low-level systems language.", rx=r"(?<![\w#+.\-])C(?=\s*(?:,|/|\||;|\)|$)|\s+(?:programming|language)\b)")
S("C#", "language", ["csharp", "c sharp"], 2, 55, [], ["Syntax and OOP", "LINQ", "async/await", ".NET tooling"],
  "Microsoft's language for .NET applications.")
S("Go", "language", ["golang"], 2, 40, [], ["Syntax and types", "Goroutines and channels", "Interfaces", "Modules"],
  "Simple, fast compiled language popular for cloud services.", rx=r"\bGo\b(?![-\s]to\b)")
S("Rust", "language", [], 3, 80, [], ["Ownership and borrowing", "Traits", "Error handling", "Cargo"],
  "Memory-safe systems language.", cs=["Rust"])
S("Kotlin", "language", [], 2, 40, ["Java"], ["Null safety", "Coroutines", "Data classes"],
  "Modern JVM language, primary language for Android.")
S("Swift", "language", [], 2, 45, [], ["Optionals", "Structs vs classes", "Protocols", "SwiftUI basics"],
  "Apple's language for iOS and macOS.", cs=["Swift"])
S("PHP", "language", [], 1, 35, [], ["Syntax", "Composer", "PDO", "OOP"], "Server-side web scripting language.")
S("Ruby", "language", [], 1, 35, [], ["Syntax", "Blocks", "Gems"], "Dynamic language, known for Rails.", cs=["Ruby"])
S("Scala", "language", [], 3, 50, ["Java"], ["Functional programming", "Case classes", "sbt"],
  "JVM language mixing OOP and functional programming.")
S("R", "language", ["r programming", "rstudio"], 2, 40, [], ["Data frames", "dplyr", "ggplot2"],
  "Language for statistics and data analysis.", rx=r"(?<![\w&'.\-])R(?=\s*(?:,|/|\||;|\)|$))")
S("MATLAB", "language", [], 2, 30, [], [], "Numerical computing environment.")
S("Dart", "language", [], 2, 30, [], ["Syntax", "async", "Null safety"], "Language behind Flutter.")
S("Bash", "language", ["shell scripting", "shell script", "bash scripting", "zsh"], 1, 15, ["Linux"],
  ["Variables and loops", "Pipes and redirection", "Scripts and cron"], "Unix shell scripting.")
S("SQL", "database", ["structured query language", "t-sql", "pl/sql", "plsql"], 1, 30, [],
  ["SELECT, filtering and sorting", "JOINs", "GROUP BY and aggregates", "Subqueries and CTEs",
   "Indexes", "Transactions"], "Language for querying relational databases.")
S("HTML", "frontend", ["html5"], 1, 10, [], ["Semantic elements", "Forms", "Accessibility basics"],
  "Markup language for web pages.")
S("CSS", "frontend", ["css3", "scss", "sass"], 1, 25, ["HTML"], ["Box model", "Flexbox", "Grid", "Responsive design"],
  "Styling language for the web.")

# ── Frontend ─────────────────────────────────────────────────────────────
S("React", "frontend", ["react.js", "reactjs", "react js"], 2, 40, ["JavaScript"],
  ["Components and JSX", "Props and state", "Hooks", "Data fetching", "Routing", "State management"],
  "Component-based UI library.")
S("Angular", "frontend", ["angularjs", "angular.js"], 2, 45, ["TypeScript"],
  ["Components and templates", "Services and DI", "RxJS", "Routing"], "Full frontend framework by Google.")
S("Vue.js", "frontend", ["vue", "vuejs", "vue 3"], 2, 30, ["JavaScript"], ["Components", "Reactivity", "Vue Router", "Pinia"],
  "Progressive frontend framework.")
S("Next.js", "frontend", ["nextjs", "next js"], 2, 25, ["React"], ["Routing", "Server components", "Data fetching", "Deployment"],
  "React framework with server rendering.")
S("Redux", "frontend", ["redux toolkit"], 2, 15, ["React"], ["Store, actions and reducers", "Redux Toolkit"], "State management library.")
S("Tailwind CSS", "frontend", ["tailwind", "tailwindcss"], 1, 10, ["CSS"], ["Utility classes", "Responsive variants"], "Utility-first CSS framework.")
S("Bootstrap", "frontend", [], 1, 8, ["CSS"], [], "CSS component framework.")
S("jQuery", "frontend", [], 1, 8, ["JavaScript"], [], "Legacy DOM manipulation library.")
S("Svelte", "frontend", ["sveltekit"], 2, 20, ["JavaScript"], [], "Compiler-based UI framework.")
S("Webpack", "frontend", ["vite"], 2, 10, ["JavaScript"], [], "Frontend bundling tools.")

# ── Backend ──────────────────────────────────────────────────────────────
S("Node.js", "backend", ["nodejs", "node js"], 2, 35, ["JavaScript"],
  ["Event loop", "npm and modules", "File system and streams", "Building HTTP servers"],
  "JavaScript runtime for servers.", cs=["Node"])
S("Express.js", "backend", ["expressjs", "express js"], 1, 15, ["Node.js"],
  ["Routing", "Middleware", "Error handling"], "Minimal Node.js web framework.", cs=["Express"])
S("Spring Boot", "backend", ["springboot", "spring-boot"], 3, 60, ["Java"],
  ["Spring IoC and dependency injection", "REST controllers", "Spring Data JPA", "Validation and error handling",
   "Spring Security basics", "Testing with JUnit and MockMvc"], "Opinionated Java framework for production services.")
S("Spring Framework", "backend", ["spring mvc", "spring framework"], 3, 40, ["Java"], [],
  "Java application framework.", rx=r"\bSpring\b(?![\s-]*Boot)(?!\s+(?:19|20)\d\d)")
S("Hibernate", "backend", ["jpa", "spring data jpa"], 2, 20, ["Java", "SQL"], ["Entities and mappings", "Relationships", "Lazy loading"],
  "Java ORM.")
S("Django", "backend", [], 2, 40, ["Python"], ["Models and ORM", "Views and URLs", "Templates", "Admin", "Django REST Framework"],
  "Batteries-included Python web framework.")
S("Flask", "backend", [], 1, 20, ["Python"], ["Routing", "Blueprints", "Request handling", "Extensions"],
  "Lightweight Python web framework.")
S("FastAPI", "backend", [], 2, 20, ["Python"], ["Path operations", "Pydantic models", "Dependency injection", "Async endpoints"],
  "Modern async Python API framework.")
S(".NET", "backend", ["dotnet", "asp.net", "asp.net core", ".net core"], 2, 50, ["C#"], [], "Microsoft application platform.")
S("Ruby on Rails", "backend", ["rails", "ror"], 2, 40, ["Ruby"], [], "Ruby web framework.")
S("Laravel", "backend", [], 2, 30, ["PHP"], [], "PHP web framework.")
S("REST APIs", "backend", ["rest api", "restful", "restful apis", "rest apis", "restful services", "web services"], 2, 20, [],
  ["HTTP methods and status codes", "Resource design", "Authentication", "Pagination and filtering",
   "Versioning", "API documentation (OpenAPI)"], "Architectural style for HTTP APIs.", cs=["REST"])
S("GraphQL", "backend", [], 2, 15, ["REST APIs"], ["Schemas and types", "Queries and mutations", "Resolvers"], "Query language for APIs.")
S("gRPC", "backend", ["protobuf", "protocol buffers"], 3, 15, ["REST APIs"], [], "RPC framework using Protocol Buffers.")
S("Microservices", "concept", ["microservice", "microservices architecture"], 3, 30, ["REST APIs", "Docker"],
  ["Service boundaries", "Inter-service communication", "Service discovery", "Observability"], "Architecture of small independent services.")
S("WebSockets", "backend", ["websocket", "socket.io"], 2, 10, ["JavaScript"], [], "Bidirectional real-time communication.")
S("Authentication", "security", ["oauth", "oauth2", "jwt", "json web token", "openid connect", "sso"], 2, 15, ["REST APIs"],
  ["Sessions vs tokens", "JWT", "OAuth 2.0 flows", "Password hashing"], "Identity and access patterns.")

# ── Databases ────────────────────────────────────────────────────────────
S("PostgreSQL", "database", ["postgres", "postgresql", "psql"], 2, 25, ["SQL"],
  ["Data types and constraints", "Indexes and EXPLAIN", "Transactions and isolation", "JSONB", "Backups"],
  "Advanced open-source relational database.")
S("MySQL", "database", ["mariadb"], 1, 20, ["SQL"], ["Schema design", "Indexes", "Replication basics"], "Popular relational database.")
S("MongoDB", "database", ["mongo", "mongoose"], 2, 20, [], ["Documents and collections", "Queries", "Aggregation", "Indexes"],
  "Document-oriented NoSQL database.")
S("Redis", "database", [], 2, 15, [], ["Data structures", "Caching patterns", "TTL and eviction", "Pub/Sub"],
  "In-memory data store used for caching and queues.")
S("SQLite", "database", [], 1, 5, ["SQL"], [], "Embedded relational database.")
S("Oracle Database", "database", ["oracle db", "oracle sql"], 2, 25, ["SQL"], [], "Enterprise relational database.")
S("SQL Server", "database", ["mssql", "microsoft sql server"], 2, 25, ["SQL"], [], "Microsoft relational database.")
S("Elasticsearch", "database", ["elastic search", "opensearch", "elk"], 2, 20, [], [], "Search and analytics engine.")
S("Cassandra", "database", [], 3, 20, [], [], "Wide-column NoSQL database.")
S("DynamoDB", "database", [], 2, 15, ["AWS"], [], "AWS managed NoSQL database.")
S("Firebase", "database", ["firestore"], 1, 12, [], [], "Google app development platform.")
S("Database Design", "concept", ["data modeling", "database modelling", "normalization", "er diagram", "erd", "schema design"],
  2, 15, ["SQL"], ["Entities and relationships", "Normalization", "Keys and constraints", "Indexing strategy"],
  "Designing relational schemas.")

# ── Cloud & DevOps ───────────────────────────────────────────────────────
S("AWS", "cloud", ["amazon web services", "ec2", "s3", "aws lambda", "cloudformation", "rds"], 2, 50, ["Linux"],
  ["IAM", "EC2 and networking (VPC)", "S3", "RDS", "Lambda", "CloudWatch"], "Amazon's cloud platform.")
S("Azure", "cloud", ["microsoft azure"], 2, 50, [], ["Resource groups", "App Service", "Azure SQL", "Azure AD"], "Microsoft's cloud platform.")
S("Google Cloud", "cloud", ["gcp", "google cloud platform", "bigquery"], 2, 50, [], [], "Google's cloud platform.")
S("Docker", "devops", ["dockerfile", "docker compose", "docker-compose", "containers", "containerization"], 2, 20, ["Linux"],
  ["Images and containers", "Writing Dockerfiles", "Volumes and networking", "Docker Compose", "Image optimisation"],
  "Container platform for packaging applications.")
S("Kubernetes", "devops", ["k8s", "kubectl", "helm", "eks", "gke", "aks"], 3, 45, ["Docker"],
  ["Pods, Deployments and Services", "ConfigMaps and Secrets", "Ingress", "Helm"], "Container orchestration platform.")
S("CI/CD", "devops", ["ci/cd", "continuous integration", "continuous delivery", "continuous deployment", "github actions",
                      "gitlab ci", "jenkins", "circleci", "travis ci"], 2, 15, ["Git"],
  ["Pipelines", "Automated tests in CI", "Build artifacts", "Deployment strategies"], "Automated build, test and deploy pipelines.")
S("Terraform", "devops", ["infrastructure as code", "iac"], 2, 20, ["AWS"], ["Providers and resources", "State", "Modules"],
  "Infrastructure-as-code tool.")
S("Ansible", "devops", [], 2, 15, ["Linux"], [], "Configuration management tool.")
S("Linux", "devops", ["unix", "ubuntu", "centos", "debian", "red hat", "rhel"], 1, 25, [],
  ["File system and permissions", "Processes", "Package management", "SSH", "Networking basics"], "Unix-like operating system.")
S("Nginx", "devops", ["apache http server", "reverse proxy"], 2, 10, ["Linux"], [], "Web server and reverse proxy.")
S("Monitoring", "devops", ["prometheus", "grafana", "datadog", "new relic", "observability", "splunk"], 2, 15, [], [], "Observing systems in production.")
S("Kafka", "backend", ["apache kafka"], 3, 25, [], ["Topics and partitions", "Producers and consumers", "Consumer groups"], "Distributed event streaming platform.")
S("RabbitMQ", "backend", ["message queue", "message queues", "amqp", "celery", "sqs"], 2, 12, [], [], "Message broker.")
S("Serverless", "cloud", ["serverless framework", "azure functions", "cloud functions"], 2, 12, [], [], "Function-as-a-service architecture.")

# ── Tools ───────────────────────────────────────────────────────────────
S("Git", "tool", ["github", "gitlab", "bitbucket", "version control"], 1, 10, [],
  ["Commits and branches", "Merging and rebasing", "Pull requests", "Resolving conflicts"], "Distributed version control.")
S("Jira", "tool", ["confluence"], 1, 4, [], [], "Issue tracking.")
S("Postman", "tool", ["insomnia"], 1, 4, ["REST APIs"], [], "API testing tool.")
S("Maven", "tool", ["gradle"], 1, 6, ["Java"], [], "Java build tools.")
S("Figma", "tool", [], 1, 8, [], [], "Collaborative design tool.")
S("Excel", "tool", ["microsoft excel", "spreadsheets", "vlookup", "pivot tables"], 1, 15, [], [], "Spreadsheet analysis.")
S("Tableau", "data", [], 1, 20, [], ["Connecting data", "Calculated fields", "Dashboards"], "Data visualisation tool.")
S("Power BI", "data", ["powerbi", "dax"], 1, 20, [], ["Data modelling", "DAX", "Reports"], "Microsoft BI tool.")
S("Agile", "concept", ["scrum", "kanban", "sprint planning"], 1, 6, [], [], "Iterative development methodology.")

# ── Testing ─────────────────────────────────────────────────────────────
S("Unit Testing", "testing", ["unit tests", "tdd", "test driven development", "test-driven development"], 2, 12, [],
  ["Test structure", "Mocks and fakes", "Coverage", "TDD"], "Testing code in isolation.")
S("JUnit", "testing", ["junit5", "mockito"], 1, 8, ["Java"], [], "Java testing framework.")
S("pytest", "testing", ["unittest"], 1, 8, ["Python"], [], "Python testing framework.")
S("Jest", "testing", ["vitest", "mocha", "react testing library"], 1, 8, ["JavaScript"], [], "JavaScript testing framework.")
S("Selenium", "testing", ["webdriver", "cypress", "playwright"], 2, 15, [], [], "Browser automation and end-to-end testing.")

# ── Data & ML ───────────────────────────────────────────────────────────
S("Pandas", "data", [], 1, 20, ["Python"], ["Series and DataFrames", "Cleaning data", "groupby", "Merging"], "Python data analysis library.")
S("NumPy", "data", ["numpy"], 1, 10, ["Python"], ["Arrays", "Broadcasting", "Vectorisation"], "Numerical computing for Python.")
S("Data Visualization", "data", ["matplotlib", "seaborn", "plotly", "d3.js", "data viz"], 1, 12, [], [], "Communicating data visually.")
S("Statistics", "data", ["statistical analysis", "hypothesis testing", "a/b testing", "probability", "regression analysis"], 2, 30, [],
  ["Descriptive statistics", "Probability", "Hypothesis testing", "Regression"], "Statistical reasoning for data work.")
S("Machine Learning", "ml", ["ml", "scikit-learn", "sklearn", "supervised learning", "unsupervised learning"], 3, 60,
  ["Python", "Statistics"], ["Supervised vs unsupervised learning", "Model evaluation", "Feature engineering",
                            "Overfitting and regularisation", "scikit-learn pipelines"], "Building predictive models from data.")
S("Deep Learning", "ml", ["neural networks", "cnn", "rnn", "lstm"], 3, 60, ["Machine Learning"], [], "Neural network methods.")
S("TensorFlow", "ml", ["keras"], 3, 30, ["Deep Learning"], [], "Deep learning framework.")
S("PyTorch", "ml", ["torch"], 3, 30, ["Deep Learning"], [], "Deep learning framework.")
S("NLP", "ml", ["natural language processing", "spacy", "nltk", "text mining"], 3, 35, ["Machine Learning"], [], "Natural language processing.")
S("LLMs", "ml", ["large language models", "llm", "generative ai", "genai", "prompt engineering", "langchain", "rag",
                 "openai api", "gemini api", "hugging face", "transformers"], 2, 25, ["Python"], [], "Building with large language models.")
S("Computer Vision", "ml", ["opencv", "image processing"], 3, 35, ["Machine Learning"], [], "Image and video understanding.")
S("Apache Spark", "data", ["pyspark", "apache spark"], 3, 30, ["Python", "SQL"], [], "Distributed data processing.", cs=["Spark"])
S("Airflow", "data", ["apache airflow"], 2, 15, ["Python"], [], "Workflow orchestration.")
S("ETL", "data", ["data pipelines", "data pipeline", "elt", "dbt"], 2, 20, ["SQL"], [], "Extract, transform, load processes.")
S("Data Warehousing", "data", ["snowflake", "redshift", "data warehouse"], 2, 20, ["SQL"], [], "Analytical data storage.")
S("Hadoop", "data", ["hdfs", "hive", "mapreduce"], 3, 25, [], [], "Distributed storage and processing.")
S("Jupyter", "data", ["jupyter notebook", "notebooks", "google colab"], 1, 3, ["Python"], [], "Interactive notebooks.")

# ── Mobile ──────────────────────────────────────────────────────────────
S("Android", "mobile", ["android sdk", "android studio", "jetpack compose"], 2, 50, ["Kotlin"], [], "Android app development.")
S("iOS", "mobile", ["swiftui", "uikit", "xcode"], 2, 50, ["Swift"], [], "iOS app development.")
S("React Native", "mobile", [], 2, 30, ["React"], [], "Cross-platform mobile with React.")
S("Flutter", "mobile", [], 2, 30, ["Dart"], [], "Cross-platform UI toolkit.")

# ── CS fundamentals & concepts ──────────────────────────────────────────
S("Data Structures", "concept", ["data structures and algorithms", "dsa", "algorithms"], 3, 80, [],
  ["Arrays and strings", "Hash maps", "Linked lists, stacks and queues", "Trees and graphs", "Sorting and searching",
   "Dynamic programming", "Big-O analysis"], "Core CS problem-solving foundations.")
S("OOP", "concept", ["object oriented programming", "object-oriented programming", "object-oriented design", "solid principles"],
  2, 15, [], ["Encapsulation, inheritance, polymorphism", "SOLID", "Composition"], "Object-oriented design.")
S("System Design", "concept", ["distributed systems", "scalability", "high availability", "load balancing"], 3, 40,
  ["REST APIs", "Database Design"], ["Scaling reads and writes", "Caching", "Queues", "Consistency trade-offs", "Capacity estimation"],
  "Designing scalable systems.")
S("Design Patterns", "concept", ["design pattern", "mvc"], 2, 15, ["OOP"], [], "Reusable solutions to common design problems.")
S("Operating Systems", "concept", ["os concepts", "multithreading", "concurrency"], 2, 25, [], [], "Processes, threads and memory.")
S("Computer Networks", "concept", ["computer networking", "tcp/ip", "dns"], 2, 20, [], [], "How networks and protocols work.")
S("Cybersecurity", "security", ["information security", "owasp", "penetration testing", "network security", "siem", "vulnerability assessment"],
  3, 40, ["Computer Networks", "Linux"], [], "Protecting systems and data.")

# ── Soft skills ─────────────────────────────────────────────────────────
S("Communication", "soft", ["communication skills", "written communication", "verbal communication", "presentation skills"], soft=True)
S("Teamwork", "soft", ["collaboration", "team player", "cross-functional"], soft=True)
S("Leadership", "soft", ["team lead", "led a team", "mentoring", "mentored"], soft=True)
S("Problem Solving", "soft", ["problem-solving", "analytical skills", "critical thinking"], soft=True)
S("Time Management", "soft", ["prioritization", "organizational skills"], soft=True)
S("Adaptability", "soft", ["fast learner", "quick learner", "self-motivated"], soft=True)
S("Stakeholder Management", "soft", ["stakeholder communication", "client communication"], soft=True)


# ── Role profiles (curated baselines) ───────────────────────────────────
# importance: core | important | nice ; level: required proficiency 1..5
ROLE_PROFILES = {
    "Backend Developer": {
        "aliases": ["backend engineer", "back end developer", "back-end developer", "server-side developer", "api developer"],
        "skills": [("REST APIs", "core", 4), ("SQL", "core", 3), ("Git", "core", 3), ("Database Design", "important", 3),
                   ("PostgreSQL", "important", 3), ("Docker", "important", 3), ("Unit Testing", "important", 3),
                   ("Authentication", "important", 3), ("Linux", "important", 2), ("Redis", "nice", 2),
                   ("Microservices", "nice", 2), ("CI/CD", "nice", 2), ("AWS", "nice", 2), ("System Design", "nice", 2),
                   ("Data Structures", "important", 3)],
        "any_of": [["Java", "Python", "Node.js", "Go", "C#"], ["Spring Boot", "Django", "Flask", "FastAPI", "Express.js", ".NET"]],
    },
    "Java Developer": {
        "aliases": ["java engineer", "java backend developer", "java software engineer"],
        "skills": [("Java", "core", 4), ("Spring Boot", "core", 4), ("REST APIs", "core", 4), ("SQL", "core", 3),
                   ("Hibernate", "important", 3), ("Git", "core", 3), ("JUnit", "important", 3), ("Maven", "important", 2),
                   ("Docker", "nice", 2), ("Microservices", "nice", 2), ("Data Structures", "important", 3), ("OOP", "core", 4)],
    },
    "Python Developer": {
        "aliases": ["python engineer", "python backend developer"],
        "skills": [("Python", "core", 4), ("REST APIs", "core", 3), ("SQL", "core", 3), ("Git", "core", 3),
                   ("pytest", "important", 3), ("Docker", "important", 2), ("Linux", "important", 2),
                   ("PostgreSQL", "nice", 2), ("Data Structures", "important", 3)],
        "any_of": [["Django", "Flask", "FastAPI"]],
    },
    "Frontend Developer": {
        "aliases": ["front end developer", "front-end developer", "frontend engineer", "ui developer", "web developer"],
        "skills": [("HTML", "core", 4), ("CSS", "core", 4), ("JavaScript", "core", 4), ("TypeScript", "important", 3),
                   ("React", "core", 3), ("Git", "core", 3), ("REST APIs", "important", 2), ("Jest", "nice", 2),
                   ("Tailwind CSS", "nice", 2), ("Next.js", "nice", 2), ("Figma", "nice", 1), ("Webpack", "nice", 2)],
    },
    "Full Stack Developer": {
        "aliases": ["full-stack developer", "fullstack developer", "full stack engineer", "mern developer", "mean developer"],
        "skills": [("HTML", "core", 3), ("CSS", "core", 3), ("JavaScript", "core", 4), ("React", "core", 3),
                   ("Node.js", "important", 3), ("REST APIs", "core", 3), ("SQL", "core", 3), ("Git", "core", 3),
                   ("TypeScript", "important", 3), ("MongoDB", "nice", 2), ("PostgreSQL", "important", 2),
                   ("Docker", "nice", 2), ("Authentication", "important", 2), ("CI/CD", "nice", 2)],
    },
    "Software Engineer": {
        "aliases": ["software developer", "sde", "software development engineer", "swe", "programmer", "application developer",
                    "graduate software engineer", "junior software engineer"],
        "skills": [("Data Structures", "core", 4), ("OOP", "core", 3), ("Git", "core", 3), ("SQL", "important", 3),
                   ("REST APIs", "important", 3), ("Unit Testing", "important", 3), ("System Design", "important", 2),
                   ("Linux", "nice", 2), ("Docker", "nice", 2), ("CI/CD", "nice", 2), ("Operating Systems", "nice", 2),
                   ("Computer Networks", "nice", 2)],
        "any_of": [["Java", "Python", "C++", "JavaScript", "Go", "C#"]],
    },
    "Data Scientist": {
        "aliases": ["data science", "ml scientist", "applied scientist"],
        "skills": [("Python", "core", 4), ("Statistics", "core", 4), ("Machine Learning", "core", 4), ("SQL", "core", 3),
                   ("Pandas", "core", 4), ("NumPy", "important", 3), ("Data Visualization", "important", 3),
                   ("Jupyter", "nice", 2), ("Deep Learning", "nice", 2), ("Git", "important", 2), ("Apache Spark", "nice", 2)],
    },
    "Data Analyst": {
        "aliases": ["business analyst", "bi analyst", "business intelligence analyst", "analytics analyst"],
        "skills": [("SQL", "core", 4), ("Excel", "core", 4), ("Data Visualization", "core", 3), ("Statistics", "important", 3),
                   ("Python", "important", 2), ("Pandas", "nice", 2), ("Communication", "core", 3)],
        "any_of": [["Tableau", "Power BI"]],
    },
    "Data Engineer": {
        "aliases": ["big data engineer", "etl developer", "analytics engineer"],
        "skills": [("SQL", "core", 4), ("Python", "core", 4), ("ETL", "core", 4), ("Data Warehousing", "important", 3),
                   ("Apache Spark", "important", 3), ("Airflow", "important", 3), ("Database Design", "important", 3),
                   ("AWS", "important", 2), ("Kafka", "nice", 2), ("Docker", "nice", 2), ("Git", "important", 2)],
    },
    "Machine Learning Engineer": {
        "aliases": ["ml engineer", "ai engineer", "mlops engineer", "deep learning engineer"],
        "skills": [("Python", "core", 4), ("Machine Learning", "core", 4), ("Deep Learning", "important", 3),
                   ("Data Structures", "important", 3), ("SQL", "important", 2), ("Docker", "important", 2),
                   ("Git", "important", 3), ("AWS", "nice", 2), ("NumPy", "important", 3), ("Pandas", "important", 3),
                   ("LLMs", "nice", 2)],
        "any_of": [["PyTorch", "TensorFlow"]],
    },
    "DevOps Engineer": {
        "aliases": ["site reliability engineer", "sre", "platform engineer", "devops"],
        "skills": [("Linux", "core", 4), ("Docker", "core", 4), ("Kubernetes", "core", 3), ("CI/CD", "core", 4),
                   ("Terraform", "important", 3), ("Bash", "core", 3), ("Git", "core", 3), ("Monitoring", "important", 3),
                   ("Computer Networks", "important", 3), ("Python", "nice", 2), ("Ansible", "nice", 2)],
        "any_of": [["AWS", "Azure", "Google Cloud"]],
    },
    "Cloud Engineer": {
        "aliases": ["cloud architect", "aws engineer", "azure engineer", "cloud developer"],
        "skills": [("Linux", "core", 3), ("Computer Networks", "core", 3), ("Terraform", "important", 3), ("Docker", "important", 3),
                   ("Kubernetes", "nice", 2), ("CI/CD", "important", 2), ("Python", "nice", 2), ("Serverless", "nice", 2),
                   ("Monitoring", "important", 2)],
        "any_of": [["AWS", "Azure", "Google Cloud"]],
    },
    "Mobile Developer": {
        "aliases": ["android developer", "ios developer", "mobile app developer", "flutter developer", "react native developer"],
        "skills": [("Git", "core", 3), ("REST APIs", "core", 3), ("Unit Testing", "important", 2), ("Firebase", "nice", 2),
                   ("OOP", "important", 3)],
        "any_of": [["Android", "iOS", "Flutter", "React Native"], ["Kotlin", "Swift", "Dart", "JavaScript"]],
    },
    "QA Engineer": {
        "aliases": ["sdet", "test engineer", "qa automation engineer", "quality assurance engineer", "software tester"],
        "skills": [("Selenium", "core", 3), ("Unit Testing", "core", 3), ("REST APIs", "important", 3), ("Postman", "important", 3),
                   ("SQL", "important", 2), ("Git", "core", 2), ("CI/CD", "important", 2), ("Agile", "important", 2)],
        "any_of": [["Java", "Python", "JavaScript"]],
    },
    "Cybersecurity Analyst": {
        "aliases": ["security analyst", "security engineer", "soc analyst", "information security analyst"],
        "skills": [("Cybersecurity", "core", 4), ("Computer Networks", "core", 4), ("Linux", "core", 3), ("Python", "important", 2),
                   ("Bash", "important", 2), ("Monitoring", "important", 2), ("Authentication", "important", 3)],
    },
}
