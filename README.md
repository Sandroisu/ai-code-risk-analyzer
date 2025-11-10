
Инструкция для локальной машины:
1. Установить переменную окружения GITHUB_TOKEN с правом чтения публичных репозиториев.
2. В файле config.json указан репозиторий square/kotlinpoet и период сбора (это конфигурируемые параметры).
3. Запустить python3 repozitory_analyzer.py в корне проекта. Сырые данные появятся в data/raw/.
5. Будет сформирован data/derived/dashboard.json.
6. Открыть index.html и нажать «Импорт JSON», выбрав data/derived/dashboard.json.

