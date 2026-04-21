#!/usr/bin/env python3
"""
Скрипт запуска тестов Vanessa Automation без vrunner.
Используется в headless-среде Docker для обхода проверки цифровой подписи.
"""

import subprocess
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
import sys

class VanessaTestRunner:
    def __init__(self, ib_path, features_path, vanessa_path):
        self.ib_path = ib_path
        self.features_path = features_path
        self.vanessa_path = vanessa_path
        self.results = []
        
    def run_tests(self):
        """Запуск тестов через 1cv8c напрямую"""
        cmd = [
            '/opt/1cv8/x86_64/8.3.27.1936/1cv8c',
            'ENTERPRISE',
            f'/F{self.ib_path}',
            f'/Execute"{self.vanessa_path}/vanessa-automation.epf"',
            f'/C"КаталогФич={self.features_path};ЗавершитьРаботуСистемы=Истина"'
        ]
        
        print(f"[INFO] Запуск тестов в {self.ib_path}...")
        print(f"[INFO] Каталог фич: {self.features_path}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                env={**os.environ, 'DISPLAY': ':99'}
            )
            
            output = result.stdout + result.stderr
            self.parse_results(output)
            return result.returncode == 0
            
        except subprocess.TimeoutExpired:
            print("[ERROR] Превышено время ожидания выполнения тестов")
            return False
        except Exception as e:
            print(f"[ERROR] Ошибка выполнения: {e}")
            return False
    
    def parse_results(self, output):
        """Парсинг лога 1С для извлечения результатов тестов"""
        # Ищем паттерны Vanessa в логе
        scenarios = re.findall(r'Сценарий: (.+?)(?:\n|$)', output)
        steps = re.findall(r'Шаг: (.+?)(?:\n|$)', output)
        errors = re.findall(r'Ошибка.*?: (.+?)(?:\n|$)', output, re.IGNORECASE)
        
        self.results = {
            'scenarios': scenarios,
            'steps': steps,
            'errors': errors,
            'total': len(scenarios),
            'passed': len(scenarios) if not errors else len(scenarios) - len(errors),
            'failed': len(errors)
        }
        
        print(f"\n[INFO] Найдено сценариев: {self.results['total']}")
        print(f"[INFO] Пройдено: {self.results['passed']}")
        print(f"[INFO] Провалено: {self.results['failed']}")
        
        if errors:
            print("\n[ERROR] Ошибки:")
            for err in errors:
                print(f"  - {err}")
    
    def generate_junit_report(self, output_path):
        """Генерация отчёта в формате JUnit XML"""
        testsuite = ET.Element('testsuite')
        testsuite.set('name', 'Vanessa Automation Tests')
        testsuite.set('tests', str(self.results['total']))
        testsuite.set('failures', str(self.results['failed']))
        testsuite.set('time', '0.0')
        testsuite.set('timestamp', datetime.now().isoformat())
        
        for scenario in self.results['scenarios']:
            testcase = ET.SubElement(testsuite, 'testcase')
            testcase.set('name', scenario)
            testcase.set('time', '0.0')
            
            if scenario in self.results['errors']:
                failure = ET.SubElement(testcase, 'failure')
                failure.set('message', 'Test failed')
        
        tree = ET.ElementTree(testsuite)
        tree.write(output_path, encoding='utf-8', xml_declaration=True)
        print(f"[INFO] Отчёт сохранён: {output_path}")

def main():
    runner = VanessaTestRunner(
        ib_path='/var/1C/infobases/demo_vkr',
        features_path='/tests/features',
        vanessa_path='/tmp/vanessa'
    )
    
    success = runner.run_tests()
    runner.generate_junit_report('/tmp/reports/junit.xml')
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
