#!/usr/bin/env python3
"""
ArchMemo Git Helper - Лесно управление на Git операции
"""

import subprocess
import sys
import os

PROJECT_DIR = "/home/koto/projects/ArchMemo-gui"

def run(cmd, cwd=PROJECT_DIR):
    """Изпълнява shell команда"""
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Грешка: {result.stderr}")
        return None
    return result.stdout.strip()

def status():
    """Показва статуса на репото"""
    print("📊 Git статус:")
    output = run("git status -s")
    if output:
        print(output)
    else:
        print("   (няма промени)")

def pull():
    """Изтегля последните промени от GitHub"""
    print("⬇️ Изтеглям от GitHub...")
    result = run("git pull origin main")
    if result is not None:
        print(result)
        print("✅ Готово!")

def push(message="Update files"):
    """Качва промените в GitHub"""
    print("📤 Качвам в GitHub...")
    
    # Проверка за промени
    status_output = run("git status -s")
    if not status_output:
        print("ℹ️ Няма промени за качване")
        return
    
    # Добавяне и commit
    run("git add .")
    run(f'git commit -m "{message}"')
    
    # Push
    result = run("git push origin main")
    if result is not None:
        print(result)
        print("✅ Качено успешно!")

def sync(message="Sync files"):
    """Синхронизира - първо pull, после push"""
    pull()
    push(message)

def help_menu():
    print("""
🛠️  ArchMemo Git Helper

Употреба: python3 git_helper.py [команда] [опции]

Команди:
    status          - Показва текущия статус
    pull            - Изтегля последните промени от GitHub
    push [msg]      - Качва промените (по подразбиране: "Update files")
    sync [msg]      - Pull + Push наведнъж
    help            - Показва това меню

Примери:
    python3 git_helper.py status
    python3 git_helper.py pull
    python3 git_helper.py push "Добавих нова функция"
    python3 git_helper.py sync "Обновяване"
""")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        help_menu()
        sys.exit(0)
    
    command = sys.argv[1].lower()
    
    # Проверка дали сме в правилната директория
    if not os.path.exists(os.path.join(PROJECT_DIR, ".git")):
        print(f"❌ Не е намерено Git репо в {PROJECT_DIR}")
        sys.exit(1)
    
    if command == "status":
        status()
    elif command == "pull":
        pull()
    elif command == "push":
        msg = sys.argv[2] if len(sys.argv) > 2 else "Update files"
        push(msg)
    elif command == "sync":
        msg = sys.argv[2] if len(sys.argv) > 2 else "Sync files"
        sync(msg)
    elif command == "help":
        help_menu()
    else:
        print(f"❌ Непозната команда: {command}")
        help_menu()
