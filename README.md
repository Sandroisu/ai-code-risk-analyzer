
Инструкция для локальной машины:
1. Установить переменную окружения GITHUB_TOKEN с правом чтения публичных репозиториев.
2. В файле config.json указан репозиторий square/kotlinpoet и период сбора (это конфигурируемые параметры).
3. Запустить python3 fetch_github.py в корне проекта. Сырые данные появятся в data/raw/.
4. Перейти в клон square/kotlinpoet и выполнить ../run_detekt.sh и ../run_ktlint.sh. В корне аналитики появятся отчёты в reports/.
5. Вернуться в корень аналитики и запустить python3 extract_features.py. Будет сформирован data/derived/dashboard.json.
6. Открыть index.html и нажать «Загрузить демо» или «Импорт JSON», выбрав data/derived/dashboard.json.

