# Архитектура HelpDesk Enterprise

Ниже представлена схема развертывания компонентов системы на корпоративном сервере.

```mermaid
graph TD
    Client[Сотрудники (Браузер / Смартфон)] -->|HTTP / WebSockets| Proxy[Шлюз / Nginx]
    
    subgraph "Корпоративный Сервер"
        Proxy -->|Проксирование на порт 8050| App[FastAPI Бэкенд (Waitress/Uvicorn)]
        App <-->|SQLAlchemy ORM| DB[(База данных SQLite / PostgreSQL)]
    end
    
    App <-->|LDAP Авторизация| AD[Active Directory]
    
    style Client fill:#e2e8f0,stroke:#64748b,stroke-width:2px
    style Proxy fill:#fef08a,stroke:#ca8a04,stroke-width:2px
    style App fill:#bfdbfe,stroke:#2563eb,stroke-width:2px
    style DB fill:#bbf7d0,stroke:#16a34a,stroke-width:2px
    style AD fill:#fbcfe8,stroke:#db2777,stroke-width:2px
