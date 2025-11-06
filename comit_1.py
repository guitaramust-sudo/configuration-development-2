#!/usr/bin/env python3
"""
Инструмент визуализации графа зависимостей для менеджера пакетов
Этап 1: Минимальный прототип с конфигурацией через CLI
"""

import argparse
import sys
import os


class DependencyVisualizer:
    """Основной класс для визуализации графа зависимостей"""

    def __init__(self):
        self.config = None

    class Config:
        """Класс для хранения и валидации конфигурационных параметров"""

        def __init__(self):
            self.package_name = None
            self.repository_url = None
            self.test_repo_path = None
            self.work_mode = None
            self.max_depth = None
            self.filter_substring = None

        def validate(self):
            """Валидация параметров конфигурации"""
            errors = []

            # Проверка обязательных параметров
            if not self.package_name:
                errors.append("Имя пакета обязательно для указания")
            elif not isinstance(self.package_name, str) or not self.package_name.strip():
                errors.append("Имя пакета должно быть непустой строкой")

            if not self.repository_url and not self.test_repo_path:
                errors.append("Необходимо указать либо URL репозитория, либо путь к тестовому репозиторию")

            if self.repository_url and self.test_repo_path:
                errors.append("Можно указать только один источник: URL репозитория ИЛИ путь к тестовому репозиторию")

            # Валидация URL
            if self.repository_url:
                if not isinstance(self.repository_url, str) or not self.repository_url.strip():
                    errors.append("URL репозитория должен быть непустой строкой")
                elif not (self.repository_url.startswith('http://') or self.repository_url.startswith('https://')):
                    errors.append("URL репозитория должен начинаться с http:// или https://")

            # Валидация пути к тестовому репозиторию
            if self.test_repo_path:
                if not isinstance(self.test_repo_path, str) or not self.test_repo_path.strip():
                    errors.append("Путь к тестовому репозиторию должен быть непустой строкой")

            # Проверка режима работы
            if self.work_mode and self.work_mode not in ['online', 'offline']:
                errors.append("Режим работы должен быть 'online' или 'offline'")

            # Автоматическое определение режима, если не указан
            if self.work_mode is None:
                if self.repository_url:
                    self.work_mode = 'online'
                elif self.test_repo_path:
                    self.work_mode = 'offline'

            # Проверка максимальной глубины
            if self.max_depth is not None:
                if not isinstance(self.max_depth, int):
                    try:
                        self.max_depth = int(self.max_depth)
                    except (ValueError, TypeError):
                        errors.append("Максимальная глубина должна быть целым числом")

                if isinstance(self.max_depth, int) and self.max_depth < 1:
                    errors.append("Максимальная глубина должна быть положительным числом")

            # Проверка существования тестового репозитория в offline режиме
            if self.work_mode == 'offline' and self.test_repo_path:
                if not os.path.exists(self.test_repo_path):
                    errors.append(f"Тестовый репозиторий не найден: {self.test_repo_path}")
                elif not os.path.isdir(self.test_repo_path):
                    errors.append(f"Путь к тестовому репозиторию должен быть директорией: {self.test_repo_path}")

            # Валидация подстроки фильтрации
            if self.filter_substring is not None:
                if not isinstance(self.filter_substring, str):
                    errors.append("Подстрока для фильтрации должна быть строкой")

            return errors

        def __str__(self):
            """Строковое представление конфигурации в формате ключ-значение"""
            config_items = [
                ("package_name", "Имя анализируемого пакета", self.package_name),
                ("repository_url", "URL репозитория", self.repository_url),
                ("test_repo_path", "Путь к тестовому репозиторию", self.test_repo_path),
                ("work_mode", "Режим работы", self.work_mode),
                ("max_depth", "Максимальная глубина анализа", self.max_depth),
                ("filter_substring", "Подстрока для фильтрации", self.filter_substring)
            ]

            result = "Текущая конфигурация:\n"
            max_key_length = max(len(key) for _, key, _ in config_items)

            for _, key, value in config_items:
                display_value = value if value is not None else 'не указано'
                result += f"  {key:<{max_key_length}} : {display_value}\n"

            return result

    def parse_arguments(self):
        """Парсинг аргументов командной строки"""
        parser = argparse.ArgumentParser(
            description='Инструмент визуализации графа зависимостей пакетов',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog='''
Примеры использования:
  python dependency_visualizer.py --package requests --url https://pypi.org/simple/
  python dependency_visualizer.py --package numpy --test-repo ./test_data --max-depth 3
  python dependency_visualizer.py --package django --url https://pypi.org/simple/ --filter "test"
  python dependency_visualizer.py --package flask --url https://pypi.org/simple/ --mode online --max-depth 2 --filter "lib"

Обязательные параметры:
  --package и (--url ИЛИ --test-repo) должны быть указаны всегда.
            '''
        )

        # Обязательные параметры
        parser.add_argument(
            '--package',
            dest='package_name',
            required=True,
            type=str,
            help='Имя анализируемого пакета (обязательно)'
        )

        # Источники данных (взаимоисключающие)
        source_group = parser.add_mutually_exclusive_group(required=True)
        source_group.add_argument(
            '--url',
            dest='repository_url',
            type=str,
            help='URL-адрес репозитория пакетов (например, https://pypi.org/simple/)'
        )
        source_group.add_argument(
            '--test-repo',
            dest='test_repo_path',
            type=str,
            help='Путь к тестовому репозиторию (директория с данными)'
        )

        # Опциональные параметры
        parser.add_argument(
            '--mode',
            dest='work_mode',
            choices=['online', 'offline'],
            help='Режим работы: online (по умолчанию с URL) или offline (с тестовым репозиторием)'
        )

        parser.add_argument(
            '--max-depth',
            dest='max_depth',
            type=int,
            help='Максимальная глубина анализа зависимостей (положительное целое число)'
        )

        parser.add_argument(
            '--filter',
            dest='filter_substring',
            type=str,
            help='Подстрока для фильтрации пакетов по имени'
        )

        return parser.parse_args()

    def create_config(self):
        """Создание и валидация конфигурации"""
        try:
            args = self.parse_arguments()
        except SystemExit:
            # argparse уже вывел сообщение об ошибке
            sys.exit(1)

        config = self.Config()
        config.package_name = args.package_name
        config.repository_url = args.repository_url
        config.test_repo_path = args.test_repo_path
        config.work_mode = args.work_mode
        config.max_depth = args.max_depth
        config.filter_substring = args.filter_substring

        # Валидация конфигурации
        errors = config.validate()
        if errors:
            self.print_error("Ошибки конфигурации:")
            for i, error in enumerate(errors, 1):
                print(f"  {i}. {error}")
            print("\nИспользуйте --help для справки по параметрам")
            sys.exit(1)

        return config

    def print_error(self, message):
        """Вывод сообщения об ошибке"""
        print(f"ОШИБКА: {message}", file=sys.stderr)

    def print_success(self, message):
        """Вывод успешного сообщения"""
        print(f"УСПЕХ: {message}")

    def demonstrate_analysis_capabilities(self, config):
        """Демонстрация возможностей анализа на основе конфигурации"""
        print("\n" + "=" * 50)
        print("ДЕМОНСТРАЦИЯ ВОЗМОЖНОСТЕЙ АНАЛИЗА")
        print("=" * 50)

        print(f"Анализируем пакет: {config.package_name}")
        print(f"Режим работы: {config.work_mode}")

        if config.work_mode == 'online':
            print(f"Источник данных: онлайн репозиторий ({config.repository_url})")
        else:
            print(f"Источник данных: локальный репозиторий ({config.test_repo_path})")

        if config.max_depth:
            print(f"Ограничение глубины анализа: {config.max_depth} уровней")
        else:
            print("Глубина анализа: неограничена")

        if config.filter_substring:
            print(f"Фильтрация пакетов: будут показаны только пакеты, содержащие '{config.filter_substring}'")
        else:
            print("Фильтрация пакетов: не применяется")

        print("\nГотов к построению графа зависимостей...")
        print("(Эта функциональность будет реализована на следующих этапах)")

    def run(self):
        """Основной метод запуска приложения"""
        try:
            print("Инструмент визуализации графа зависимостей")
            print("Этап 1: Минимальный прототип с конфигурацией\n")

            # Создание и валидация конфигурации
            self.config = self.create_config()

            # Вывод всех параметров в формате ключ-значение (требование этапа)
            print(self.config)

            # Демонстрация работы с параметрами
            self.demonstrate_analysis_capabilities(self.config)

            # Симуляция анализа зависимостей
            print("\n" + "=" * 50)
            print("СИМУЛЯЦИЯ АНАЛИЗА ЗАВИСИМОСТЕЙ")
            print("=" * 50)

            # Простая симуляция графа зависимостей на основе конфигурации
            self.simulate_dependency_analysis()

            self.print_success("Конфигурация успешно применена!")

        except KeyboardInterrupt:
            self.print_error("Программа прервана пользователем")
            sys.exit(1)
        except Exception as e:
            self.print_error(f"Неожиданная ошибка: {e}")
            sys.exit(1)

    def simulate_dependency_analysis(self):
        """Симуляция анализа зависимостей для демонстрации"""
        # Простой пример графа зависимостей
        sample_dependencies = {
            'requests': ['urllib3', 'chardet', 'certifi'],
            'urllib3': ['brotli', 'pyOpenSSL'],
            'chardet': [],
            'certifi': [],
            'brotli': [],
            'pyOpenSSL': ['cryptography']
        }

        current_package = self.config.package_name
        max_depth = self.config.max_depth or 3
        filter_str = self.config.filter_substring

        print(f"\nСимуляция анализа зависимостей для '{current_package}':")

        def analyze_deps(package, depth=0, visited=None):
            if visited is None:
                visited = set()

            if depth > max_depth:
                return []

            if package in visited:
                return ["(циклическая зависимость)"]

            visited.add(package)

            # Применяем фильтрацию
            if filter_str and filter_str not in package:
                return []

            deps = sample_dependencies.get(package, [])
            result = [f"{'  ' * depth}├── {package}"]

            for dep in deps:
                result.extend(analyze_deps(dep, depth + 1, visited.copy()))

            return result

        try:
            tree = analyze_deps(current_package)
            if tree:
                for line in tree:
                    print(line)
            else:
                print("  (зависимости не найдены или отфильтрованы)")
        except KeyError:
            print(f"  (пакет '{current_package}' не найден в тестовых данных)")


def main():
    """Точка входа в приложение"""
    visualizer = DependencyVisualizer()
    visualizer.run()


if __name__ == "__main__":
    main()