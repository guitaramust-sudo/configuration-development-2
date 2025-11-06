#!/usr/bin/env python3
"""
Инструмент визуализации графа зависимостей для менеджера пакетов
Этап 2: Сбор данных для NuGet пакетов
"""

import argparse
import sys
import os
import xml.etree.ElementTree as ET
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
import json


class DependencyVisualizer:
    """Основной класс для визуализации графа зависимостей"""

    def __init__(self):
        self.config = None
        self.nuget_service_index = None

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

    class NuGetClient:
        """Клиент для работы с NuGet репозиторием"""

        def __init__(self, base_url):
            self.base_url = base_url.rstrip('/')
            self.services = {}

        def get_service_url(self, service_type="PackageBaseAddress/3.0.0"):
            """Получение URL сервиса из service index"""
            try:
                if not self.services:
                    # Получаем service index
                    service_index_url = f"{self.base_url}/index.json"
                    request = Request(service_index_url, headers={'User-Agent': 'DependencyVisualizer/1.0'})

                    with urlopen(request) as response:
                        data = json.loads(response.read().decode())

                    # Кэшируем сервисы
                    for resource in data.get('resources', []):
                        self.services[resource['@type']] = resource['@id']

                return self.services.get(service_type)
            except Exception as e:
                raise Exception(f"Ошибка получения service index: {e}")

        def get_package_versions(self, package_name):
            """Получение списка версий пакета"""
            try:
                service_url = self.get_service_url()
                if not service_url:
                    raise Exception("Не найден сервис PackageBaseAddress")

                package_url = f"{service_url}{package_name.lower()}/index.json"
                request = Request(package_url, headers={'User-Agent': 'DependencyVisualizer/1.0'})

                with urlopen(request) as response:
                    data = json.loads(response.read().decode())

                return data.get('versions', [])
            except HTTPError as e:
                if e.code == 404:
                    raise Exception(f"Пакет '{package_name}' не найден в репозитории")
                else:
                    raise Exception(f"HTTP ошибка при получении версий: {e.code}")
            except Exception as e:
                raise Exception(f"Ошибка получения версий пакета: {e}")

        def get_package_dependencies(self, package_name, version=None):
            """Получение зависимостей пакета"""
            try:
                if not version:
                    versions = self.get_package_versions(package_name)
                    if not versions:
                        raise Exception(f"Не найдены версии для пакета '{package_name}'")
                    version = versions[-1]  # Берем последнюю версию

                service_url = self.get_service_url()
                nuspec_url = f"{service_url}{package_name.lower()}/{version}/{package_name.lower()}.nuspec"
                request = Request(nuspec_url, headers={'User-Agent': 'DependencyVisualizer/1.0'})

                with urlopen(request) as response:
                    nuspec_content = response.read().decode()

                return self.parse_nuspec_dependencies(nuspec_content)

            except HTTPError as e:
                if e.code == 404:
                    raise Exception(f"Метаданные пакета '{package_name}' версии '{version}' не найдены")
                else:
                    raise Exception(f"HTTP ошибка при получении зависимостей: {e.code}")
            except Exception as e:
                raise Exception(f"Ошибка получения зависимостей: {e}")

        def parse_nuspec_dependencies(self, nuspec_content):
            """Парсинг зависимостей из .nuspec файла"""
            try:
                root = ET.fromstring(nuspec_content)

                # Находим namespace
                ns = {'ns': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {'ns': ''}

                # Ищем зависимости
                dependencies = []
                metadata = root.find('ns:metadata', ns) if ns['ns'] else root.find('metadata')

                if metadata is not None:
                    deps_element = metadata.find('ns:dependencies', ns) if ns['ns'] else metadata.find('dependencies')
                    if deps_element is not None:
                        for group in deps_element.findall('ns:group', ns) if ns['ns'] else deps_element.findall(
                                'group'):
                            for dep in group.findall('ns:dependency', ns) if ns['ns'] else group.findall('dependency'):
                                dep_id = dep.get('id')
                                if dep_id:
                                    dependencies.append(dep_id)

                        # Также проверяем зависимости без группы
                        for dep in deps_element.findall('ns:dependency', ns) if ns['ns'] else deps_element.findall(
                                'dependency'):
                            dep_id = dep.get('id')
                            if dep_id:
                                dependencies.append(dep_id)

                return list(set(dependencies))  # Убираем дубликаты

            except ET.ParseError as e:
                raise Exception(f"Ошибка парсинга .nuspec файла: {e}")
            except Exception as e:
                raise Exception(f"Ошибка анализа зависимостей: {e}")

    def parse_arguments(self):
        """Парсинг аргументов командной строки"""
        parser = argparse.ArgumentParser(
            description='Инструмент визуализации графа зависимостей пакетов (NuGet)',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog='''
Примеры использования:
  python comit_1.py --package Newtonsoft.Json --url https://api.nuget.org/v3/index.json
  python comit_1.py --package Newtonsoft.Json --url https://api.nuget.org/v3/index.json --max-depth 3
  python comit_1.py --package Microsoft.Extensions.Logging --url https://api.nuget.org/v3/index.json --filter "Extensions"

Обязательные параметры:
  --package и --url должны быть указаны всегда.
            '''
        )

        # Обязательные параметры
        parser.add_argument(
            '--package',
            dest='package_name',
            required=True,
            type=str,
            help='Имя анализируемого пакета NuGet (обязательно)'
        )

        # Источники данных
        parser.add_argument(
            '--url',
            dest='repository_url',
            type=str,
            required=True,
            help='URL-адрес NuGet репозитория (например, https://api.nuget.org/v3/index.json)'
        )

        # Опциональные параметры
        parser.add_argument(
            '--mode',
            dest='work_mode',
            choices=['online', 'offline'],
            help='Режим работы: online (по умолчанию) или offline'
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
        config.test_repo_path = None  # Для этого этапа не используется
        config.work_mode = args.work_mode or 'online'
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

    def get_dependencies(self, config):
        """Получение прямых зависимостей пакета"""
        try:
            print(f"\nПолучение зависимостей для пакета: {config.package_name}")
            print(f"Репозиторий: {config.repository_url}")
            print("-" * 50)

            # Создаем клиент NuGet
            nuget_client = self.NuGetClient(config.repository_url)

            # Получаем зависимости
            dependencies = nuget_client.get_package_dependencies(config.package_name)

            # Применяем фильтрацию, если указана
            if config.filter_substring:
                dependencies = [dep for dep in dependencies if config.filter_substring.lower() in dep.lower()]

            return dependencies

        except Exception as e:
            self.print_error(f"Ошибка при получении зависимостей: {e}")
            return []

    def display_dependencies(self, package_name, dependencies):
        """Вывод прямых зависимостей на экран"""
        if not dependencies:
            print(f"Пакет '{package_name}' не имеет прямых зависимостей.")
            return

        print(f"Прямые зависимости пакета '{package_name}':")
        print("-" * 40)

        for i, dep in enumerate(sorted(dependencies), 1):
            print(f"{i:2d}. {dep}")

        print(f"\nВсего найдено зависимостей: {len(dependencies)}")

    def run(self):
        """Основной метод запуска приложения"""
        try:
            print("Инструмент визуализации графа зависимостей")
            print("Этап 2: Сбор данных для NuGet пакетов\n")

            # Создание и валидация конфигурации
            self.config = self.create_config()

            # Вывод всех параметров в формате ключ-значение
            print(self.config)

            # Получение и вывод прямых зависимостей
            dependencies = self.get_dependencies(self.config)

            # Вывод зависимостей на экран (требование этапа 2)
            self.display_dependencies(self.config.package_name, dependencies)

            # Демонстрация дополнительной информации
            if dependencies and self.config.max_depth and self.config.max_depth > 1:
                print(f"\nПримечание: Установлена максимальная глубина анализа: {self.config.max_depth}")
                print("На следующих этапах будет реализован рекурсивный анализ зависимостей.")

            self.print_success("Анализ зависимостей завершен!")

        except KeyboardInterrupt:
            self.print_error("Программа прервана пользователем")
            sys.exit(1)
        except Exception as e:
            self.print_error(f"Неожиданная ошибка: {e}")
            sys.exit(1)


def main():
    """Точка входа в приложение"""
    visualizer = DependencyVisualizer()
    visualizer.run()


if __name__ == "__main__":
    main()