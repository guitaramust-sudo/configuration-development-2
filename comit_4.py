#!/usr/bin/env python3
"""
Инструмент визуализации графа зависимостей для менеджера пакетов
Этап 4: Дополнительные операции - обратные зависимости
"""

import argparse
import sys
import os
import xml.etree.ElementTree as ET
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
import json
from collections import deque, defaultdict
import re
import glob


class DependencyVisualizer:
    """Основной класс для визуализации графа зависимостей"""

    def __init__(self):
        self.config = None
        self.dependency_graph = defaultdict(list)
        self.reverse_dependency_graph = defaultdict(list)
        self.visited_packages = set()
        self.cycle_detected = False
        self.operation_mode = 'forward'  # 'forward' или 'reverse'

    class Config:
        """Класс для хранения и валидации конфигурационных параметров"""

        def __init__(self):
            self.package_name = None
            self.repository_url = None
            self.test_repo_path = None
            self.work_mode = None
            self.max_depth = None
            self.filter_substring = None
            self.reverse_mode = False

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
                elif not os.path.exists(self.test_repo_path):
                    errors.append(f"Тестовый репозиторий не найден: {self.test_repo_path}")

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
                ("filter_substring", "Подстрока для фильтрации", self.filter_substring),
                ("reverse_mode", "Режим обратных зависимостей", "включен" if self.reverse_mode else "выключен")
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

    class OfflineNuGetRepository:
        """Класс для работы с оффлайн NuGet репозиторием"""

        def __init__(self, repo_path):
            self.repo_path = repo_path
            self.packages = {}
            self.load_offline_repository()

        def load_offline_repository(self):
            """Загрузка оффлайн репозитория из .nuspec файлов"""
            try:
                # Ищем все .nuspec файлы в директории и поддиректориях
                nuspec_files = glob.glob(os.path.join(self.repo_path, "**", "*.nuspec"), recursive=True)

                if not nuspec_files:
                    raise Exception(f"Не найдены .nuspec файлы в {self.repo_path}")

                for nuspec_file in nuspec_files:
                    try:
                        package_name, dependencies = self.parse_nuspec_file(nuspec_file)
                        self.packages[package_name] = dependencies
                    except Exception as e:
                        print(f"Ошибка загрузки {nuspec_file}: {e}")

                if not self.packages:
                    raise Exception("Не удалось загрузить ни одного пакета из .nuspec файлов")

                print(f"Оффлайн репозиторий загружен: {len(self.packages)} пакетов")

            except Exception as e:
                raise Exception(f"Ошибка загрузки оффлайн репозитория: {e}")

        def parse_nuspec_file(self, file_path):
            """Парсинг .nuspec файла"""
            try:
                tree = ET.parse(file_path)
                root = tree.getroot()

                # Находим namespace
                ns = {'ns': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {'ns': ''}

                # Получаем имя пакета
                metadata = root.find('ns:metadata', ns) if ns['ns'] else root.find('metadata')
                if metadata is None:
                    raise Exception("Метаданные не найдены")

                package_id = metadata.find('ns:id', ns) if ns['ns'] else metadata.find('id')
                if package_id is None:
                    raise Exception("ID пакета не найден")

                package_name = package_id.text

                # Ищем зависимости
                dependencies = []
                deps_element = metadata.find('ns:dependencies', ns) if ns['ns'] else metadata.find('dependencies')

                if deps_element is not None:
                    for group in deps_element.findall('ns:group', ns) if ns['ns'] else deps_element.findall('group'):
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

                return package_name, list(set(dependencies))

            except ET.ParseError as e:
                raise Exception(f"Ошибка парсинга XML: {e}")
            except Exception as e:
                raise Exception(f"Ошибка чтения .nuspec файла: {e}")

        def get_package_dependencies(self, package_name):
            """Получение зависимостей пакета из оффлайн репозитория"""
            return self.packages.get(package_name, [])

        def get_all_packages(self):
            """Получение списка всех пакетов в репозитории"""
            return list(self.packages.keys())

    class TestRepository:
        """Класс для работы с тестовым репозиторием (A->B C формат)"""

        def __init__(self, file_path):
            self.file_path = file_path
            self.dependency_graph = {}
            self.load_test_repository()

        def load_test_repository(self):
            """Загрузка тестового репозитория из файла"""
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()

                # Парсим зависимости в формате: A -> B C D
                lines = content.split('\n')
                for line in lines:
                    line = line.strip()
                    if '->' in line:
                        parts = line.split('->')
                        if len(parts) == 2:
                            package = parts[0].strip()
                            dependencies = [dep.strip() for dep in parts[1].split() if dep.strip()]
                            self.dependency_graph[package] = dependencies

                if not self.dependency_graph:
                    raise Exception("Тестовый репозиторий не содержит корректных данных")

            except FileNotFoundError:
                raise Exception(f"Файл тестового репозитория не найден: {self.file_path}")
            except Exception as e:
                raise Exception(f"Ошибка загрузки тестового репозитория: {e}")

        def get_package_dependencies(self, package_name):
            """Получение зависимостей пакета из тестового репозитория"""
            return self.dependency_graph.get(package_name, [])

        def get_all_packages(self):
            """Получение списка всех пакетов в репозитории"""
            return list(self.dependency_graph.keys())

        def build_reverse_dependencies(self):
            """Построение графа обратных зависимостей"""
            reverse_graph = defaultdict(list)
            for package, dependencies in self.dependency_graph.items():
                for dep in dependencies:
                    reverse_graph[dep].append(package)
            return reverse_graph

    def parse_arguments(self):
        """Парсинг аргументов командной строки"""
        parser = argparse.ArgumentParser(
            description='Инструмент визуализации графа зависимостей пакетов (NuGet) - Этап 4',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog='''
Примеры использования:
  # Прямые зависимости (режим по умолчанию):
  python comit_1.py --package Newtonsoft.Json --url https://api.nuget.org/v3/index.json
  python comit_1.py --package A --test-repo simple_test.txt --mode offline

  # ОБРАТНЫЕ зависимости (новый режим):
  python comit_1.py --package D --test-repo simple_test.txt --mode offline --reverse
  python comit_1.py --package Microsoft.Extensions.DependencyInjection.Abstractions --test-repo ./offline_nuget --mode offline --reverse

  # Комбинированные параметры:
  python comit_1.py --package C --test-repo complex_test.txt --mode offline --reverse --max-depth 2
  python comit_1.py --package Abstractions --test-repo ./offline_nuget --mode offline --reverse --filter "Microsoft"

Формат тестового репозитория:
  A -> B C
  B -> C D
  C -> E
  D -> 
  E -> A  # циклическая зависимость

Обязательные параметры:
  --package и (--url ИЛИ --test-repo) должны быть указаны.
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
            help='URL-адрес NuGet репозитория (например, https://api.nuget.org/v3/index.json)'
        )
        source_group.add_argument(
            '--test-repo',
            dest='test_repo_path',
            type=str,
            help='Путь к тестовому репозиторию (файл A->B C или директория с .nuspec файлами)'
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

        # Новый параметр для обратных зависимостей
        parser.add_argument(
            '--reverse',
            dest='reverse_mode',
            action='store_true',
            help='Режим обратных зависимостей (показывает кто зависит от данного пакета)'
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
        config.reverse_mode = args.reverse_mode

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

    def should_skip_package(self, package_name):
        """Проверка, нужно ли пропустить пакет согласно фильтру"""
        if self.config.filter_substring and self.config.filter_substring.lower() in package_name.lower():
            return True
        return False

    def detect_repository_type(self, repo_path):
        """Определение типа репозитория"""
        if os.path.isfile(repo_path):
            return 'test_format'
        elif os.path.isdir(repo_path):
            # Проверяем, есть ли .nuspec файлы в директории
            nuspec_files = glob.glob(os.path.join(repo_path, "**", "*.nuspec"), recursive=True)
            if nuspec_files:
                return 'nuspec_offline'
            else:
                raise Exception(f"В директории {repo_path} не найдены .nuspec файлы")
        else:
            raise Exception(f"Путь {repo_path} не является файлом или директорией")

    def get_dependencies(self, package_name):
        """Получение зависимостей пакета в зависимости от режима и типа репозитория"""
        try:
            if self.config.work_mode == 'online':
                nuget_client = self.NuGetClient(self.config.repository_url)
                return nuget_client.get_package_dependencies(package_name)
            else:
                # Определяем тип оффлайн репозитория
                repo_type = self.detect_repository_type(self.config.test_repo_path)

                if repo_type == 'nuspec_offline':
                    offline_repo = self.OfflineNuGetRepository(self.config.test_repo_path)
                    return offline_repo.get_package_dependencies(package_name)
                else:  # test_format
                    test_repo = self.TestRepository(self.config.test_repo_path)
                    return test_repo.get_package_dependencies(package_name)

        except Exception as e:
            print(f"Ошибка получения зависимостей для {package_name}: {e}")
            return []

    def build_complete_dependency_graph(self):
        """Построение полного графа зависимостей для обратного анализа"""
        try:
            print("Построение полного графа зависимостей для анализа...")

            if self.config.work_mode == 'online':
                # Для онлайн режима невозможно построить полный граф
                raise Exception("Обратные зависимости недоступны в онлайн режиме. Используйте тестовый репозиторий.")
            else:
                repo_type = self.detect_repository_type(self.config.test_repo_path)

                if repo_type == 'nuspec_offline':
                    offline_repo = self.OfflineNuGetRepository(self.config.test_repo_path)
                    all_packages = offline_repo.get_all_packages()

                    # Строим полный граф зависимостей
                    for package in all_packages:
                        dependencies = offline_repo.get_package_dependencies(package)
                        self.dependency_graph[package] = dependencies

                        # Строим обратный граф
                        for dep in dependencies:
                            self.reverse_dependency_graph[dep].append(package)

                else:  # test_format
                    test_repo = self.TestRepository(self.config.test_repo_path)
                    self.dependency_graph = test_repo.dependency_graph

                    # Строим обратный граф
                    for package, dependencies in self.dependency_graph.items():
                        for dep in dependencies:
                            self.reverse_dependency_graph[dep].append(package)

            print(
                f"Граф построен: {len(self.dependency_graph)} пакетов, {sum(len(deps) for deps in self.reverse_dependency_graph.values())} обратных связей")

        except Exception as e:
            raise Exception(f"Ошибка построения графа: {e}")

    def bfs_build_dependency_graph(self, start_package, current_depth=0, path=None):
        """Построение графа зависимостей с помощью BFS с рекурсией"""
        if path is None:
            path = []

        # Проверка максимальной глубины
        if self.config.max_depth and current_depth >= self.config.max_depth:
            return

        # Проверка циклических зависимостей
        if start_package in path:
            print(f"Обнаружена циклическая зависимость: {' -> '.join(path + [start_package])}")
            self.cycle_detected = True
            return

        # Проверка фильтрации
        if self.should_skip_package(start_package):
            print(f"Пропущен пакет '{start_package}' (фильтр: '{self.config.filter_substring}')")
            return

        # Если пакет уже посещен на этом уровне, пропускаем
        if start_package in self.visited_packages:
            return

        self.visited_packages.add(start_package)

        print(f"{'  ' * current_depth}Анализ пакета: {start_package} (глубина: {current_depth})")

        try:
            # Получение зависимостей
            dependencies = self.get_dependencies(start_package)

            # Добавляем зависимости в граф
            self.dependency_graph[start_package] = dependencies

            # Рекурсивный анализ зависимостей
            for dep in dependencies:
                self.bfs_build_dependency_graph(dep, current_depth + 1, path + [start_package])

        except Exception as e:
            print(f"{'  ' * current_depth}Ошибка при анализе пакета {start_package}: {e}")

    def bfs_build_reverse_dependency_graph(self, start_package, current_depth=0, path=None):
        """Построение графа ОБРАТНЫХ зависимостей с помощью BFS с рекурсией"""
        if path is None:
            path = []

        # Проверка максимальной глубины
        if self.config.max_depth and current_depth >= self.config.max_depth:
            return

        # Проверка циклических зависимостей
        if start_package in path:
            print(f"Обнаружена циклическая зависимость: {' -> '.join(path + [start_package])}")
            self.cycle_detected = True
            return

        # Проверка фильтрации
        if self.should_skip_package(start_package):
            print(f"Пропущен пакет '{start_package}' (фильтр: '{self.config.filter_substring}')")
            return

        # Если пакет уже посещен на этом уровне, пропускаем
        if start_package in self.visited_packages:
            return

        self.visited_packages.add(start_package)

        print(f"{'  ' * current_depth}Анализ пакета: {start_package} (глубина: {current_depth})")

        try:
            # Получаем пакеты, которые зависят от текущего
            dependents = self.reverse_dependency_graph.get(start_package, [])

            # Добавляем в граф (в обратном направлении)
            self.dependency_graph[start_package] = dependents

            # Рекурсивный анализ обратных зависимостей
            for dependent in dependents:
                self.bfs_build_reverse_dependency_graph(dependent, current_depth + 1, path + [start_package])

        except Exception as e:
            print(f"{'  ' * current_depth}Ошибка при анализе пакета {start_package}: {e}")

    def display_dependency_graph(self):
        """Отображение построенного графа зависимостей"""
        if not self.dependency_graph:
            print("Граф зависимостей пуст.")
            return

        print("\n" + "=" * 60)
        if self.config.reverse_mode:
            print("ГРАФ ОБРАТНЫХ ЗАВИСИМОСТЕЙ")
        else:
            print("ГРАФ ПРЯМЫХ ЗАВИСИМОСТЕЙ")
        print("=" * 60)

        total_dependencies = 0
        for package, dependencies in sorted(self.dependency_graph.items()):
            if self.config.reverse_mode:
                # Для обратных зависимостей показываем кто зависит от пакета
                deps_str = ", ".join(dependencies) if dependencies else "(никто не зависит)"
                print(f"{package} <- {deps_str}")
            else:
                # Для прямых зависимостей показываем от кого зависит пакет
                deps_str = ", ".join(dependencies) if dependencies else "(нет зависимостей)"
                print(f"{package} -> {deps_str}")
            total_dependencies += len(dependencies)

        print(f"\nСтатистика:")
        print(f"  Всего пакетов в графе: {len(self.dependency_graph)}")
        print(f"  Всего связей: {total_dependencies}")
        print(f"  Максимальная глубина: {self.config.max_depth or 'не ограничена'}")
        print(f"  Фильтр: '{self.config.filter_substring or 'не применен'}'")
        print(f"  Режим: {'ОБРАТНЫЕ зависимости' if self.config.reverse_mode else 'прямые зависимости'}")

        if self.cycle_detected:
            print(f"  Обнаружены циклические зависимости!")

    def display_detailed_analysis(self):
        """Детальный анализ графа"""
        if not self.dependency_graph:
            return

        print("\n" + "=" * 60)
        print("ДЕТАЛЬНЫЙ АНАЛИЗ ГРАФА")
        print("=" * 60)

        if self.config.reverse_mode:
            start_package = self.config.package_name
            dependents = self.dependency_graph.get(start_package, [])

            print(f"Пакет '{start_package}' используется следующими пакетами:")
            if dependents:
                for i, dep in enumerate(sorted(dependents), 1):
                    print(f"  {i:2d}. {dep}")
            else:
                print("  (пакет не используется другими пакетами)")
        else:
            # Анализ уровней зависимостей для прямого графа
            levels = {}
            for package in self.dependency_graph:
                level = self.calculate_dependency_level(package)
                if level not in levels:
                    levels[level] = []
                levels[level].append(package)

            print("Распределение по уровням зависимостей:")
            for level in sorted(levels.keys()):
                packages = sorted(levels[level])
                print(f"  Уровень {level}: {', '.join(packages)}")

            # Пакеты без зависимостей
            leaf_packages = [pkg for pkg, deps in self.dependency_graph.items() if not deps]
            if leaf_packages:
                print(f"\nПакеты без зависимостей ({len(leaf_packages)}): {', '.join(sorted(leaf_packages))}")

    def calculate_dependency_level(self, package):
        """Вычисление уровня зависимости пакета"""
        if not self.dependency_graph[package]:
            return 0

        max_child_level = 0
        for dep in self.dependency_graph[package]:
            if dep in self.dependency_graph:
                child_level = self.calculate_dependency_level(dep)
                max_child_level = max(max_child_level, child_level)

        return max_child_level + 1

    def run(self):
        """Основной метод запуска приложения"""
        try:
            print("Инструмент визуализации графа зависимостей")
            print("Этап 4: Дополнительные операции - обратные зависимости\n")

            # Создание и валидация конфигурации
            self.config = self.create_config()

            # Вывод всех параметров в формате ключ-значение
            print(self.config)

            if self.config.reverse_mode:
                # РЕЖИМ ОБРАТНЫХ ЗАВИСИМОСТЕЙ
                print("\n" + "=" * 60)
                print("АНАЛИЗ ОБРАТНЫХ ЗАВИСИМОСТЕЙ")
                print("=" * 60)
                print(f"Поиск пакетов, которые зависят от: {self.config.package_name}")

                # Сначала строим полный граф
                self.build_complete_dependency_graph()

                # Затем строим граф обратных зависимостей
                print(f"\nПостроение графа обратных зависимостей (BFS)...")
                self.bfs_build_reverse_dependency_graph(self.config.package_name)

            else:
                # РЕЖИМ ПРЯМЫХ ЗАВИСИМОСТЕЙ (предыдущая функциональность)
                print("\n" + "=" * 60)
                print("ПОСТРОЕНИЕ ГРАФА ПРЯМЫХ ЗАВИСИМОСТЕЙ (BFS)")
                print("=" * 60)

                self.bfs_build_dependency_graph(self.config.package_name)

            # Отображение результатов
            self.display_dependency_graph()
            self.display_detailed_analysis()

            self.print_success("Анализ графа зависимостей завершен!")

        except KeyboardInterrupt:
            self.print_error("Программа прервана пользователем")
            sys.exit(1)
        except Exception as e:
            self.print_error(f"Неожиданная ошибка: {e}")
            sys.exit(1)


def create_sample_nuspec_files():
    """Создание примеров .nuspec файлов для оффлайн режима"""
    sample_packages = {
        'Newtonsoft.Json.nuspec': '''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd">
  <metadata>
    <id>Newtonsoft.Json</id>
    <version>13.0.1</version>
    <authors>James Newton-King</authors>
    <description>Json.NET is a popular high-performance JSON framework for .NET</description>
    <dependencies>
      <group targetFramework=".NETStandard2.0" />
    </dependencies>
  </metadata>
</package>''',

        'Microsoft.Extensions.Logging.nuspec': '''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd">
  <metadata>
    <id>Microsoft.Extensions.Logging</id>
    <version>6.0.0</version>
    <authors>Microsoft</authors>
    <description>Logging infrastructure default implementation for Microsoft.Extensions.Logging.</description>
    <dependencies>
      <group targetFramework=".NETStandard2.0">
        <dependency id="Microsoft.Extensions.DependencyInjection" version="6.0.0" />
        <dependency id="Microsoft.Extensions.Logging.Abstractions" version="6.0.0" />
        <dependency id="Microsoft.Extensions.Options" version="6.0.0" />
        <dependency id="System.Diagnostics.DiagnosticSource" version="6.0.0" />
      </group>
    </dependencies>
  </metadata>
</package>''',

        'Microsoft.Extensions.DependencyInjection.nuspec': '''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd">
  <metadata>
    <id>Microsoft.Extensions.DependencyInjection</id>
    <version>6.0.0</version>
    <authors>Microsoft</authors>
    <description>Default implementation of dependency injection for Microsoft.Extensions.DependencyInjection.</description>
    <dependencies>
      <group targetFramework=".NETStandard2.0">
        <dependency id="Microsoft.Extensions.DependencyInjection.Abstractions" version="6.0.0" />
      </group>
    </dependencies>
  </metadata>
</package>''',

        'Microsoft.Extensions.Logging.Abstractions.nuspec': '''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd">
  <metadata>
    <id>Microsoft.Extensions.Logging.Abstractions</id>
    <version>6.0.0</version>
    <authors>Microsoft</authors>
    <description>Logging abstractions for Microsoft.Extensions.Logging.</description>
    <dependencies>
      <group targetFramework=".NETStandard2.0" />
    </dependencies>
  </metadata>
</package>''',

        'Microsoft.Extensions.Options.nuspec': '''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd">
  <metadata>
    <id>Microsoft.Extensions.Options</id>
    <version>6.0.0</version>
    <authors>Microsoft</authors>
    <description>Options infrastructure for Microsoft.Extensions.Options.</description>
    <dependencies>
      <group targetFramework=".NETStandard2.0">
        <dependency id="Microsoft.Extensions.DependencyInjection.Abstractions" version="6.0.0" />
        <dependency id="Microsoft.Extensions.Primitives" version="6.0.0" />
      </group>
    </dependencies>
  </metadata>
</package>''',

        'Microsoft.Extensions.DependencyInjection.Abstractions.nuspec': '''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd">
  <metadata>
    <id>Microsoft.Extensions.DependencyInjection.Abstractions</id>
    <version>6.0.0</version>
    <authors>Microsoft</authors>
    <description>Abstractions for dependency injection.</description>
    <dependencies>
      <group targetFramework=".NETStandard2.0" />
    </dependencies>
  </metadata>
</package>'''
    }

    os.makedirs('offline_nuget', exist_ok=True)
    for filename, content in sample_packages.items():
        filepath = os.path.join('offline_nuget', filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Создан файл: {filepath}")


def create_test_repository_files():
    """Создание тестовых файлов репозитория для демонстрации"""
    test_files = {
        'simple_test.txt': '''
A -> B C
B -> D
C -> D E
D -> 
E -> F
F -> 
''',
        'cycle_test.txt': '''
A -> B
B -> C
C -> A
D -> E
E -> D F
F -> 
''',
        'complex_test.txt': '''
A -> B C D
B -> E F
C -> F G
D -> H
E -> I
F -> I J
G -> K
H -> L
I -> M
J -> M N
K -> O
L -> P
M -> 
N -> 
O -> 
P -> 
'''
    }

    for filename, content in test_files.items():
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content.strip())
        print(f"Создан тестовый файл: {filename}")


def main():
    """Точка входа в приложение"""
    visualizer = DependencyVisualizer()

    # Создание тестовых файлов при первом запуске (для демонстрации)
    if not os.path.exists('simple_test.txt'):
        print("Создание тестовых файлов репозитория...")
        create_test_repository_files()

    if not os.path.exists('offline_nuget'):
        print("Создание примеров .nuspec файлов...")
        create_sample_nuspec_files()
        print("\n" + "=" * 60)

    visualizer.run()


if __name__ == "__main__":
    main()