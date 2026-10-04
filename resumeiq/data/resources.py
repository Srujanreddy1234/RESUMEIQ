"""Curated learning resources.

Only official documentation and well-established learning platforms are listed.
The AI is never allowed to invent URLs. Where no specific curated link exists,
we generate a clearly-labelled *search* link (YouTube / Coursera search pages)
instead of guessing a video or course URL.
"""
from urllib.parse import quote_plus


def R(skill, title, platform, rtype, difficulty, hours, url, free=True):
    return {"skill": skill, "title": title, "platform": platform, "type": rtype, "difficulty": difficulty,
            "est_hours": hours, "url": url, "is_free": free}


RESOURCES = [
    # Languages
    R("Python", "The Python Tutorial", "python.org", "documentation", "beginner", 15, "https://docs.python.org/3/tutorial/"),
    R("Python", "CS50's Introduction to Programming with Python", "Harvard CS50", "course", "beginner", 40, "https://cs50.harvard.edu/python/"),
    R("Java", "Learn Java", "dev.java (Oracle)", "documentation", "beginner", 20, "https://dev.java/learn/"),
    R("Java", "Java Programming MOOC", "University of Helsinki", "course", "beginner", 60, "https://java-programming.mooc.fi/"),
    R("JavaScript", "JavaScript Guide", "MDN Web Docs", "documentation", "beginner", 15, "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide"),
    R("JavaScript", "The Modern JavaScript Tutorial", "javascript.info", "course", "intermediate", 30, "https://javascript.info/"),
    R("TypeScript", "TypeScript Handbook", "typescriptlang.org", "documentation", "beginner", 10, "https://www.typescriptlang.org/docs/handbook/intro.html"),
    R("C++", "LearnCpp.com", "LearnCpp", "course", "beginner", 60, "https://www.learncpp.com/"),
    R("C#", "C# documentation", "Microsoft Learn", "documentation", "beginner", 20, "https://learn.microsoft.com/en-us/dotnet/csharp/"),
    R("Go", "A Tour of Go", "go.dev", "course", "beginner", 8, "https://go.dev/tour/"),
    R("Go", "Effective Go", "go.dev", "documentation", "intermediate", 4, "https://go.dev/doc/effective_go"),
    R("Rust", "The Rust Programming Language", "rust-lang.org", "book", "beginner", 40, "https://doc.rust-lang.org/book/"),
    R("Kotlin", "Kotlin docs: Getting started", "kotlinlang.org", "documentation", "beginner", 10, "https://kotlinlang.org/docs/getting-started.html"),
    R("Swift", "The Swift Programming Language", "swift.org", "book", "beginner", 25, "https://docs.swift.org/swift-book/documentation/the-swift-programming-language/"),
    R("SQL", "SQLBolt interactive lessons", "SQLBolt", "practice", "beginner", 5, "https://sqlbolt.com/"),
    R("SQL", "PostgreSQL Tutorial: The SQL Language", "postgresql.org", "documentation", "beginner", 6, "https://www.postgresql.org/docs/current/tutorial-sql.html"),
    R("SQL", "SQL practice problems", "LeetCode", "practice", "intermediate", 15, "https://leetcode.com/problemset/database/"),
    R("HTML", "Learn web development", "MDN Web Docs", "course", "beginner", 10, "https://developer.mozilla.org/en-US/docs/Learn"),
    R("CSS", "CSS: Cascading Style Sheets", "MDN Web Docs", "documentation", "beginner", 15, "https://developer.mozilla.org/en-US/docs/Web/CSS"),
    R("Bash", "The Linux command line (Linux Journey)", "Linux Journey", "course", "beginner", 8, "https://labex.io/linuxjourney"),
    # Frontend
    R("React", "Learn React", "react.dev", "documentation", "beginner", 15, "https://react.dev/learn"),
    R("React", "Full Stack Open", "University of Helsinki", "course", "intermediate", 60, "https://fullstackopen.com/en/"),
    R("Angular", "Angular tutorials", "angular.dev", "documentation", "beginner", 12, "https://angular.dev/tutorials"),
    R("Vue.js", "Vue.js Guide", "vuejs.org", "documentation", "beginner", 10, "https://vuejs.org/guide/introduction.html"),
    R("Next.js", "Learn Next.js", "nextjs.org", "course", "intermediate", 12, "https://nextjs.org/learn"),
    R("Tailwind CSS", "Tailwind CSS docs", "tailwindcss.com", "documentation", "beginner", 4, "https://tailwindcss.com/docs"),
    R("Redux", "Redux Essentials", "redux.js.org", "documentation", "intermediate", 6, "https://redux.js.org/tutorials/essentials/part-1-overview-concepts"),
    # Backend
    R("Node.js", "Learn Node.js", "nodejs.org", "documentation", "beginner", 10, "https://nodejs.org/en/learn"),
    R("Express.js", "Express: Getting started", "expressjs.com", "documentation", "beginner", 4, "https://expressjs.com/en/starter/installing.html"),
    R("Spring Boot", "Spring Boot guides", "spring.io", "documentation", "beginner", 10, "https://spring.io/guides"),
    R("Spring Boot", "Spring Boot reference documentation", "spring.io", "documentation", "intermediate", 20, "https://docs.spring.io/spring-boot/index.html"),
    R("Spring Boot", "Building a RESTful Web Service", "spring.io", "documentation", "beginner", 2, "https://spring.io/guides/gs/rest-service"),
    R("Spring Framework", "Spring Framework documentation", "spring.io", "documentation", "intermediate", 20, "https://docs.spring.io/spring-framework/reference/"),
    R("Hibernate", "Hibernate ORM documentation", "hibernate.org", "documentation", "intermediate", 10, "https://hibernate.org/orm/documentation/"),
    R("Django", "Writing your first Django app", "djangoproject.com", "documentation", "beginner", 8, "https://docs.djangoproject.com/en/stable/intro/tutorial01/"),
    R("Flask", "Flask tutorial", "Pallets", "documentation", "beginner", 6, "https://flask.palletsprojects.com/en/stable/tutorial/"),
    R("FastAPI", "FastAPI tutorial - user guide", "fastapi.tiangolo.com", "documentation", "beginner", 8, "https://fastapi.tiangolo.com/tutorial/"),
    R(".NET", "ASP.NET Core documentation", "Microsoft Learn", "documentation", "beginner", 15, "https://learn.microsoft.com/en-us/aspnet/core/"),
    R("REST APIs", "HTTP overview", "MDN Web Docs", "documentation", "beginner", 4, "https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview"),
    R("REST APIs", "HTTP response status codes", "MDN Web Docs", "documentation", "beginner", 1, "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status"),
    R("REST APIs", "OpenAPI Specification - Getting started", "OpenAPI Initiative", "documentation", "intermediate", 3, "https://learn.openapis.org/"),
    R("GraphQL", "Learn GraphQL", "graphql.org", "documentation", "beginner", 6, "https://graphql.org/learn/"),
    R("gRPC", "gRPC introduction", "grpc.io", "documentation", "intermediate", 4, "https://grpc.io/docs/what-is-grpc/introduction/"),
    R("Microservices", "Microservice architecture patterns", "microservices.io", "documentation", "intermediate", 8, "https://microservices.io/patterns/"),
    R("Authentication", "OWASP Authentication Cheat Sheet", "OWASP", "documentation", "intermediate", 2, "https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html"),
    R("Authentication", "Introduction to JSON Web Tokens", "jwt.io", "documentation", "beginner", 1, "https://jwt.io/introduction"),
    R("Kafka", "Apache Kafka quickstart", "kafka.apache.org", "documentation", "intermediate", 4, "https://kafka.apache.org/quickstart"),
    R("RabbitMQ", "RabbitMQ tutorials", "rabbitmq.com", "documentation", "beginner", 5, "https://www.rabbitmq.com/tutorials"),
    # Databases
    R("PostgreSQL", "PostgreSQL tutorial", "postgresql.org", "documentation", "beginner", 8, "https://www.postgresql.org/docs/current/tutorial.html"),
    R("PostgreSQL", "Using EXPLAIN", "postgresql.org", "documentation", "intermediate", 3, "https://www.postgresql.org/docs/current/using-explain.html"),
    R("MySQL", "MySQL tutorial", "dev.mysql.com", "documentation", "beginner", 6, "https://dev.mysql.com/doc/refman/8.0/en/tutorial.html"),
    R("MongoDB", "MongoDB University", "MongoDB", "course", "beginner", 15, "https://learn.mongodb.com/"),
    R("Redis", "Redis documentation", "redis.io", "documentation", "beginner", 6, "https://redis.io/docs/latest/"),
    R("Redis", "Redis University", "Redis", "course", "intermediate", 10, "https://university.redis.io/"),
    R("Elasticsearch", "Elasticsearch guide", "elastic.co", "documentation", "intermediate", 10, "https://www.elastic.co/guide/index.html"),
    R("Database Design", "Designing Data-Intensive Applications", "O'Reilly (Martin Kleppmann)", "book", "advanced", 40, "https://dataintensive.net/", free=False),
    # Cloud & DevOps
    R("AWS", "AWS Skill Builder", "Amazon Web Services", "course", "beginner", 20, "https://skillbuilder.aws/"),
    R("AWS", "Getting started with AWS", "Amazon Web Services", "documentation", "beginner", 6, "https://aws.amazon.com/getting-started/"),
    R("AWS", "AWS Certified Cloud Practitioner", "Amazon Web Services", "certification", "beginner", 30, "https://aws.amazon.com/certification/certified-cloud-practitioner/", free=False),
    R("AWS", "AWS Certified Solutions Architect - Associate", "Amazon Web Services", "certification", "intermediate", 60, "https://aws.amazon.com/certification/certified-solutions-architect-associate/", free=False),
    R("Azure", "Azure training", "Microsoft Learn", "course", "beginner", 20, "https://learn.microsoft.com/en-us/training/azure/"),
    R("Azure", "Microsoft Certified: Azure Fundamentals (AZ-900)", "Microsoft", "certification", "beginner", 25, "https://learn.microsoft.com/en-us/credentials/certifications/azure-fundamentals/", free=False),
    R("Google Cloud", "Google Cloud training", "Google Cloud", "course", "beginner", 20, "https://cloud.google.com/learn/training"),
    R("Google Cloud", "Associate Cloud Engineer certification", "Google Cloud", "certification", "intermediate", 50, "https://cloud.google.com/learn/certification/cloud-engineer", free=False),
    R("Docker", "Docker: Get started", "docs.docker.com", "documentation", "beginner", 6, "https://docs.docker.com/get-started/"),
    R("Docker", "Dockerfile best practices", "docs.docker.com", "documentation", "intermediate", 2, "https://docs.docker.com/build/building/best-practices/"),
    R("Docker", "Docker Compose overview", "docs.docker.com", "documentation", "intermediate", 3, "https://docs.docker.com/compose/"),
    R("Kubernetes", "Learn Kubernetes basics", "kubernetes.io", "documentation", "beginner", 8, "https://kubernetes.io/docs/tutorials/kubernetes-basics/"),
    R("Kubernetes", "Certified Kubernetes Administrator (CKA)", "CNCF", "certification", "advanced", 80, "https://www.cncf.io/training/certification/cka/", free=False),
    R("CI/CD", "GitHub Actions documentation", "GitHub Docs", "documentation", "beginner", 5, "https://docs.github.com/en/actions"),
    R("Terraform", "Terraform tutorials", "HashiCorp", "documentation", "beginner", 10, "https://developer.hashicorp.com/terraform/tutorials"),
    R("Ansible", "Ansible getting started", "docs.ansible.com", "documentation", "beginner", 6, "https://docs.ansible.com/ansible/latest/getting_started/index.html"),
    R("Linux", "Linux Journey", "Linux Journey", "course", "beginner", 15, "https://labex.io/linuxjourney"),
    R("Linux", "OverTheWire: Bandit", "OverTheWire", "practice", "beginner", 10, "https://overthewire.org/wargames/bandit/"),
    R("Nginx", "NGINX beginner's guide", "nginx.org", "documentation", "beginner", 2, "https://nginx.org/en/docs/beginners_guide.html"),
    R("Monitoring", "Prometheus: Getting started", "prometheus.io", "documentation", "beginner", 4, "https://prometheus.io/docs/prometheus/latest/getting_started/"),
    # Tools
    R("Git", "Pro Git book", "git-scm.com", "book", "beginner", 12, "https://git-scm.com/book/en/v2"),
    R("Git", "Learn Git Branching", "learngitbranching.js.org", "practice", "beginner", 4, "https://learngitbranching.js.org/"),
    R("Agile", "The Scrum Guide", "scrumguides.org", "documentation", "beginner", 1, "https://scrumguides.org/scrum-guide.html"),
    R("Power BI", "Power BI training", "Microsoft Learn", "course", "beginner", 15, "https://learn.microsoft.com/en-us/training/powerplatform/power-bi"),
    R("Tableau", "Tableau free training videos", "Tableau", "course", "beginner", 10, "https://www.tableau.com/learn/training"),
    # Testing
    R("JUnit", "JUnit 5 user guide", "junit.org", "documentation", "beginner", 4, "https://junit.org/junit5/docs/current/user-guide/"),
    R("pytest", "pytest: Get started", "docs.pytest.org", "documentation", "beginner", 3, "https://docs.pytest.org/en/stable/getting-started.html"),
    R("Jest", "Jest: Getting started", "jestjs.io", "documentation", "beginner", 3, "https://jestjs.io/docs/getting-started"),
    R("Selenium", "Selenium documentation", "selenium.dev", "documentation", "beginner", 6, "https://www.selenium.dev/documentation/"),
    R("Unit Testing", "Martin Fowler: Unit Test", "martinfowler.com", "documentation", "beginner", 1, "https://martinfowler.com/bliki/UnitTest.html"),
    # Data & ML
    R("Pandas", "pandas: Getting started", "pandas.pydata.org", "documentation", "beginner", 6, "https://pandas.pydata.org/docs/getting_started/index.html"),
    R("Pandas", "Kaggle Learn: Pandas", "Kaggle", "course", "beginner", 4, "https://www.kaggle.com/learn/pandas"),
    R("NumPy", "NumPy: Learn", "numpy.org", "documentation", "beginner", 4, "https://numpy.org/learn/"),
    R("Data Visualization", "Kaggle Learn: Data Visualization", "Kaggle", "course", "beginner", 4, "https://www.kaggle.com/learn/data-visualization"),
    R("Statistics", "Khan Academy: Statistics and probability", "Khan Academy", "course", "beginner", 30, "https://www.khanacademy.org/math/statistics-probability"),
    R("Machine Learning", "Machine Learning Crash Course", "Google for Developers", "course", "beginner", 15, "https://developers.google.com/machine-learning/crash-course"),
    R("Machine Learning", "scikit-learn: Getting started", "scikit-learn.org", "documentation", "intermediate", 10, "https://scikit-learn.org/stable/getting_started.html"),
    R("Machine Learning", "Kaggle Learn: Intro to Machine Learning", "Kaggle", "course", "beginner", 3, "https://www.kaggle.com/learn/intro-to-machine-learning"),
    R("Deep Learning", "Practical Deep Learning for Coders", "fast.ai", "course", "intermediate", 40, "https://course.fast.ai/"),
    R("PyTorch", "PyTorch tutorials", "pytorch.org", "documentation", "intermediate", 15, "https://pytorch.org/tutorials/"),
    R("TensorFlow", "TensorFlow tutorials", "tensorflow.org", "documentation", "intermediate", 15, "https://www.tensorflow.org/tutorials"),
    R("NLP", "Hugging Face NLP course", "Hugging Face", "course", "intermediate", 20, "https://huggingface.co/learn/nlp-course"),
    R("LLMs", "Hugging Face LLM course", "Hugging Face", "course", "intermediate", 20, "https://huggingface.co/learn/llm-course"),
    R("Apache Spark", "Spark quick start", "spark.apache.org", "documentation", "intermediate", 4, "https://spark.apache.org/docs/latest/quick-start.html"),
    R("Airflow", "Airflow tutorial", "airflow.apache.org", "documentation", "intermediate", 6, "https://airflow.apache.org/docs/apache-airflow/stable/tutorial/index.html"),
    R("ETL", "dbt Learn", "dbt Labs", "course", "intermediate", 10, "https://learn.getdbt.com/"),
    # Mobile
    R("Android", "Android Basics with Compose", "Android Developers", "course", "beginner", 40, "https://developer.android.com/courses/android-basics-compose/course"),
    R("iOS", "Develop in Swift tutorials", "Apple Developer", "course", "beginner", 30, "https://developer.apple.com/tutorials/develop-in-swift"),
    R("Flutter", "Flutter: Get started", "flutter.dev", "documentation", "beginner", 10, "https://docs.flutter.dev/get-started"),
    R("React Native", "React Native: Getting started", "reactnative.dev", "documentation", "beginner", 8, "https://reactnative.dev/docs/getting-started"),
    # CS fundamentals
    R("Data Structures", "NeetCode roadmap", "NeetCode", "practice", "intermediate", 60, "https://neetcode.io/roadmap"),
    R("Data Structures", "LeetCode problem set", "LeetCode", "practice", "intermediate", 80, "https://leetcode.com/problemset/"),
    R("Data Structures", "HackerRank: Data Structures", "HackerRank", "practice", "beginner", 20, "https://www.hackerrank.com/domains/data-structures"),
    R("System Design", "The System Design Primer", "GitHub (donnemartin)", "documentation", "intermediate", 25, "https://github.com/donnemartin/system-design-primer"),
    R("OOP", "CS50x", "Harvard CS50", "course", "beginner", 80, "https://cs50.harvard.edu/x/"),
    R("Design Patterns", "Refactoring.Guru design patterns", "Refactoring.Guru", "documentation", "intermediate", 10, "https://refactoring.guru/design-patterns"),
    R("Operating Systems", "Operating Systems: Three Easy Pieces", "OSTEP (free online book)", "book", "intermediate", 40, "https://pages.cs.wisc.edu/~remzi/OSTEP/"),
    R("Computer Networks", "Cloudflare Learning Center", "Cloudflare", "documentation", "beginner", 6, "https://www.cloudflare.com/learning/"),
    R("Cybersecurity", "OWASP Top 10", "OWASP", "documentation", "beginner", 4, "https://owasp.org/www-project-top-ten/"),
    R("Cybersecurity", "TryHackMe learning paths", "TryHackMe", "practice", "beginner", 30, "https://tryhackme.com/paths"),
]


def search_links(skill_name):
    """Clearly-labelled search links. These are search result pages, not specific videos/courses."""
    q = quote_plus(f"{skill_name} tutorial")
    return [
        {"skill": skill_name, "title": f"YouTube search: {skill_name} tutorials", "platform": "YouTube",
         "type": "youtube", "difficulty": "beginner", "est_hours": None,
         "url": f"https://www.youtube.com/results?search_query={q}", "is_free": True, "is_search_link": True},
        {"skill": skill_name, "title": f"Coursera search: {skill_name}", "platform": "Coursera",
         "type": "course", "difficulty": "beginner", "est_hours": None,
         "url": f"https://www.coursera.org/search?query={quote_plus(skill_name)}", "is_free": False, "is_search_link": True},
    ]
