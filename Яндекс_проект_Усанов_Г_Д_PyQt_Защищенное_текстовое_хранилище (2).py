import sys
import hashlib
import secrets

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QDialog
from PyQt6.QtWidgets import QTextEdit, QLabel, QListWidget, QListWidgetItem, QMenu, QFileDialog, QMessageBox
from PyQt6.QtWidgets import QLineEdit, QInputDialog
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QDir, QFile, QFileInfo, QIODevice, QByteArray, QStandardPaths, QDateTime
from PyQt6.QtSql import QSqlDatabase, QSqlQuery

database = None

def create_database():
    global database

    folder = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )

    QDir().mkpath(folder)

    database = QSqlDatabase.addDatabase('QSQLITE')
    database.setDatabaseName(folder + '/storage.db')

    if not database.open():
        QMessageBox.critical(None, 'Ошибка', 'Не удалось открыть базу данных')
        return False

    query = QSqlQuery(database)

    query.exec('''
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            is_text INTEGER
        )
    ''')

    query.exec('''
        CREATE TABLE IF NOT EXISTS texts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            content TEXT,
            date_added TEXT,
            modified_at TEXT,
            password TEXT,
            salt TEXT,
            folder_id INTEGER
        )
    ''')

    query.exec('''
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            content BLOB,
            date_added TEXT,
            modified_at TEXT,
            folder_id INTEGER
        )
    ''')

    query.exec('PRAGMA table_info(texts)')
    columns = []

    while query.next():
        columns.append(query.value(1))

    for column, definition in [
        ('modified_at', 'TEXT'),
        ('password', 'TEXT'),
        ('salt', 'TEXT'),
        ('folder_id', 'INTEGER')
    ]:
        if column not in columns:
            query.exec(f'ALTER TABLE texts ADD COLUMN {column} {definition}')

    query.exec('PRAGMA table_info(images)')
    columns = []

    while query.next():
        columns.append(query.value(1))

    for column, definition in [
        ('modified_at', 'TEXT'),
        ('folder_id', 'INTEGER')
    ]:
        if column not in columns:
            query.exec(f'ALTER TABLE images ADD COLUMN {column} {definition}')

    query.exec(
        'UPDATE texts SET modified_at = date_added WHERE modified_at IS NULL'
    )
    query.exec(
        'UPDATE images SET modified_at = date_added WHERE modified_at IS NULL'
    )

    return True

def hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        bytes.fromhex(salt),
        200000
    ).hex()

class TextEditor(QDialog):
    def __init__(self, record_id=None, folder_id=None):
        super().__init__()

        self.record_id = record_id
        self.folder_id = folder_id

        self.setWindowTitle('Текстовый редактор')
        self.resize(800, 450)

        layout = QVBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText('Название документа')
        self.text_edit = QTextEdit()

        if record_id:
            query = QSqlQuery(database)
            query.prepare('SELECT name, content FROM texts WHERE id = ?')
            query.addBindValue(record_id)
            query.exec()

            if query.next():
                self.name_edit.setText(query.value(0))
                self.text_edit.setPlainText(query.value(1))

        save_button = QPushButton('Сохранить')
        close_button = QPushButton('Закрыть')

        save_button.clicked.connect(self.save_text)
        close_button.clicked.connect(self.close)

        layout.addWidget(QLabel('Название документа'))
        layout.addWidget(self.name_edit)
        layout.addWidget(QLabel('Текстовый документ'))
        layout.addWidget(self.text_edit)
        layout.addWidget(save_button)
        layout.addWidget(close_button)

        self.setLayout(layout)

    def save_text(self):
        name = self.name_edit.text().strip()
        content = self.text_edit.toPlainText()

        if not name:
            QMessageBox.warning(self, 'Ошибка', 'Введите название документа')
            return

        query = QSqlQuery(database)
        current_date = QDateTime.currentDateTime().toString(Qt.DateFormat.ISODate)

        if self.record_id:
            query.prepare(
                'UPDATE texts SET name = ?, content = ?, modified_at = ? WHERE id = ?'
            )
            query.addBindValue(name)
            query.addBindValue(content)
            query.addBindValue(current_date)
            query.addBindValue(self.record_id)

        else:
            password, accepted = QInputDialog.getText(
                self,
                'Пароль документа',
                'Придумайте пароль:',
                QLineEdit.EchoMode.Password
            )

            if not accepted:
                return

            if not password:
                QMessageBox.warning(self, 'Ошибка', 'Введите пароль')
                return

            salt = secrets.token_hex(16)
            password_hash = hash_password(password, salt)

            query.prepare(
                '''
                INSERT INTO texts
                (name, content, date_added, modified_at, password, salt, folder_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                '''
            )

            query.addBindValue(name)
            query.addBindValue(content)
            query.addBindValue(current_date)
            query.addBindValue(current_date)
            query.addBindValue(password_hash)
            query.addBindValue(salt)
            query.addBindValue(self.folder_id)

        if query.exec():
            if not self.record_id:
                self.record_id = int(query.lastInsertId())

            QMessageBox.information(self, 'Сохранение', 'Текст сохранён')
        else:
            QMessageBox.warning(self, 'Ошибка', 'Не удалось сохранить текст')

class FilesWindow(QDialog):
    def __init__(self, title, is_text, sort_mode, folder_id=None):
        super().__init__()

        self.is_text = is_text
        self.sort_mode = sort_mode
        self.folder_id = folder_id

        self.setWindowTitle(title)
        self.resize(500, 400)

        layout = QVBoxLayout()

        self.search = QLineEdit()
        self.search.setPlaceholderText('Поиск по названию')

        self.files_list = QListWidget()

        open_button = QPushButton('Открыть')
        delete_button = QPushButton('Удалить')
        close_button = QPushButton('Закрыть')

        open_button.clicked.connect(self.open_file)
        delete_button.clicked.connect(self.delete_file)
        close_button.clicked.connect(self.close)

        self.files_list.itemDoubleClicked.connect(self.open_file)
        self.search.textChanged.connect(self.update_list)

        layout.addWidget(QLabel(title))
        layout.addWidget(self.search)
        layout.addWidget(self.files_list)

        # Кнопка добавления текста в текущую папку
        if self.is_text:
            add_button = QPushButton('Добавить текст')
            add_button.clicked.connect(self.add_text)
            layout.addWidget(add_button)

        layout.addWidget(open_button)
        layout.addWidget(delete_button)
        layout.addWidget(close_button)

        self.setLayout(layout)
        self.update_list()

    def add_text(self):
        editor = TextEditor(folder_id=self.folder_id)
        editor.exec()
        self.update_list()

    def update_list(self):
        self.files_list.clear()
        search_text = self.search.text().lower()
        query = QSqlQuery(database)

        table = 'texts' if self.is_text else 'images'

        if self.is_text:
            if self.sort_mode == 'size':
                sorting = 'LENGTH(content)'
            elif self.sort_mode == 'date':
                sorting = 'date_added'
            else:
                sorting = 'name COLLATE NOCASE'
        else:
            if self.sort_mode == 'date':
                sorting = 'date_added'
            else:
                sorting = 'name COLLATE NOCASE'

        query.prepare(
            f'SELECT id, name, modified_at FROM {table} '
            f'WHERE folder_id = ? ORDER BY {sorting}'
        )
        query.addBindValue(self.folder_id)
        query.exec()

        while query.next():
            record_id = query.value(0)
            name = query.value(1)
            modified = query.value(2) or ''

            if search_text in name.lower():
                date_text = ''

                if modified:
                    date = QDateTime.fromString(
                        modified,
                        Qt.DateFormat.ISODate
                    )
                    date_text = date.toString('dd.MM.yyyy HH:mm')

                item = QListWidgetItem(f'{name} ({date_text})')
                item.setData(Qt.ItemDataRole.UserRole, record_id)
                self.files_list.addItem(item)

    def open_file(self, item=None):
        if item is None:
            item = self.files_list.currentItem()

        if item:
            record_id = item.data(Qt.ItemDataRole.UserRole)

            if self.is_text:
                query = QSqlQuery(database)
                query.prepare(
                    'SELECT password, salt FROM texts WHERE id = ?'
                )
                query.addBindValue(record_id)
                query.exec()

                if not query.next():
                    return

                saved_hash = query.value(0)
                salt = query.value(1)

                password, accepted = QInputDialog.getText(
                    self,
                    'Защита документа',
                    'Введите пароль:',
                    QLineEdit.EchoMode.Password
                )

                if not accepted:
                    return

                if not saved_hash or not salt:
                    QMessageBox.warning(
                        self,
                        'Ошибка',
                        'У документа отсутствует пароль'
                    )
                    return

                if hash_password(password, salt) != saved_hash:
                    QMessageBox.warning(self, 'Ошибка', 'Неверный пароль')
                    return

                editor = TextEditor(record_id)
                editor.exec()
                self.update_list()

            else:
                viewer = ImageViewer(record_id)
                viewer.exec()

    def delete_file(self):
        item = self.files_list.currentItem()

        if item:
            record_id = item.data(Qt.ItemDataRole.UserRole)

            answer = QMessageBox.question(
                self,
                'Удаление',
                'Удалить выбранный файл?',
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No
            )

            if answer == QMessageBox.StandardButton.Yes:
                query = QSqlQuery(database)

                if self.is_text:
                    query.prepare('DELETE FROM texts WHERE id = ?')
                else:
                    query.prepare('DELETE FROM images WHERE id = ?')

                query.addBindValue(record_id)
                query.exec()

                self.update_list()

class ImageViewer(QDialog):
    def __init__(self, record_id):
        super().__init__()

        self.setWindowTitle('Просмотр изображения')
        self.resize(600, 450)

        layout = QVBoxLayout()
        image_label = QLabel()

        query = QSqlQuery(database)
        query.prepare('SELECT content FROM images WHERE id = ?')
        query.addBindValue(record_id)
        query.exec()

        if query.next():
            image = QPixmap()
            image.loadFromData(bytes(query.value(0)))

            image_label.setPixmap(
                image.scaled(
                    550,
                    380,
                    Qt.AspectRatioMode.KeepAspectRatio
                )
            )

        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(image_label)
        self.setLayout(layout)

class FoldersWindow(QDialog):
    def __init__(self, is_text, sort_mode):
        super().__init__()

        self.is_text = is_text
        self.sort_mode = sort_mode

        self.setWindowTitle('Мои папки')
        self.resize(500, 400)

        layout = QVBoxLayout()

        self.folders_list = QListWidget()

        add_button = QPushButton('Создать папку')
        open_button = QPushButton('Открыть папку')
        delete_button = QPushButton('Удалить папку')
        close_button = QPushButton('Закрыть')

        add_button.clicked.connect(self.add_folder)
        open_button.clicked.connect(self.open_folder)
        delete_button.clicked.connect(self.delete_folder)
        close_button.clicked.connect(self.close)

        self.folders_list.itemDoubleClicked.connect(self.open_folder)

        layout.addWidget(QLabel('Папки'))
        layout.addWidget(self.folders_list)
        layout.addWidget(add_button)
        layout.addWidget(open_button)
        layout.addWidget(delete_button)
        layout.addWidget(close_button)

        self.setLayout(layout)
        self.load_folders()

    def load_folders(self):
        self.folders_list.clear()

        query = QSqlQuery(database)
        query.prepare(
            'SELECT id, name FROM folders WHERE is_text = ? ORDER BY name'
        )
        query.addBindValue(1 if self.is_text else 0)
        query.exec()

        while query.next():
            item = QListWidgetItem(query.value(1))
            item.setData(Qt.ItemDataRole.UserRole, query.value(0))
            self.folders_list.addItem(item)

    def add_folder(self):
        name, accepted = QInputDialog.getText(
            self,
            'Новая папка',
            'Введите название папки:'
        )

        if not accepted or not name.strip():
            return

        query = QSqlQuery(database)
        query.prepare(
            'INSERT INTO folders (name, is_text) VALUES (?, ?)'
        )
        query.addBindValue(name.strip())
        query.addBindValue(1 if self.is_text else 0)

        if query.exec():
            self.load_folders()
        else:
            QMessageBox.warning(self, 'Ошибка', 'Не удалось создать папку')

    def open_folder(self, item=None):
        if item is None:
            item = self.folders_list.currentItem()

        if item:
            folder_id = item.data(Qt.ItemDataRole.UserRole)

            window = FilesWindow(
                item.text(),
                self.is_text,
                self.sort_mode,
                folder_id
            )
            window.exec()

    def delete_folder(self):
        item = self.folders_list.currentItem()

        if not item:
            return

        answer = QMessageBox.question(
            self,
            'Удаление',
            'Удалить папку и все файлы внутри неё?',
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        folder_id = item.data(Qt.ItemDataRole.UserRole)
        table = 'texts' if self.is_text else 'images'

        query = QSqlQuery(database)
        query.prepare(f'DELETE FROM {table} WHERE folder_id = ?')
        query.addBindValue(folder_id)
        query.exec()

        query.prepare('DELETE FROM folders WHERE id = ?')
        query.addBindValue(folder_id)
        query.exec()

        self.load_folders()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('Защищённое хранилище')
        self.resize(900, 500)

        self.text_sort = 'name'
        self.image_sort = 'name'

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        sort_button = QPushButton('Отсортировать')
        sort_button.setFixedHeight(80)

        sort_menu = QMenu(self)

        text_menu = sort_menu.addMenu('Текстовые файлы')

        text_menu.addAction('По длине').triggered.connect(
            lambda: self.set_sort('size', True)
        )
        text_menu.addAction('По названию').triggered.connect(
            lambda: self.set_sort('name', True)
        )
        text_menu.addAction('По дате добавления').triggered.connect(
            lambda: self.set_sort('date', True)
        )

        image_menu = sort_menu.addMenu('Изображения')

        image_menu.addAction('По названию').triggered.connect(
            lambda: self.set_sort('name', False)
        )
        image_menu.addAction('По дате добавления').triggered.connect(
            lambda: self.set_sort('date', False)
        )

        sort_button.setMenu(sort_menu)
        main_layout.addWidget(sort_button)

        columns_layout = QHBoxLayout()

        text_layout = QVBoxLayout()

        add_text_button = QPushButton('Добавить текст')
        add_text_button.setFixedHeight(400)

        my_text_button = QPushButton('Мои файлы (txt)')
        my_text_button.setFixedHeight(50)

        add_text_button.clicked.connect(self.open_editor)
        my_text_button.clicked.connect(self.open_text_files)

        text_layout.addWidget(add_text_button)
        text_layout.addWidget(my_text_button)

        image_layout = QVBoxLayout()

        add_image_button = QPushButton('Добавить изображение')
        add_image_button.setFixedHeight(400)

        my_image_button = QPushButton('Мои файлы (изображения)')
        my_image_button.setFixedHeight(50)

        add_image_button.clicked.connect(self.add_image)
        my_image_button.clicked.connect(self.open_image_files)

        image_layout.addWidget(add_image_button)
        image_layout.addWidget(my_image_button)

        columns_layout.addLayout(text_layout)
        columns_layout.addLayout(image_layout)

        main_layout.addLayout(columns_layout)

    def set_sort(self, mode, is_text):
        if is_text:
            self.text_sort = mode
        else:
            self.image_sort = mode

    def open_editor(self):
        editor = TextEditor()
        editor.exec()

    def open_text_files(self):
        window = FoldersWindow(True, self.text_sort)
        window.exec()

    def open_image_files(self):
        window = FoldersWindow(False, self.image_sort)
        window.exec()

    def add_image(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            'Выберите изображение',
            '',
            'Изображения (*.png *.jpg *.jpeg *.bmp)'
        )

        if filepath:
            name, accepted = QInputDialog.getText(
                self,
                'Название изображения',
                'Введите название:',
                text=QFileInfo(filepath).fileName()
            )

            if accepted and name.strip():
                file = QFile(filepath)

                if file.open(QIODevice.OpenModeFlag.ReadOnly):
                    image_data = bytes(file.readAll())
                    file.close()

                    query = QSqlQuery(database)
                    current_date = QDateTime.currentDateTime().toString(
                        Qt.DateFormat.ISODate
                    )

                    query.prepare(
                        '''
                        INSERT INTO images
                        (name, content, date_added, modified_at, folder_id)
                        VALUES (?, ?, ?, ?, NULL)
                        '''
                    )

                    query.addBindValue(name.strip())
                    query.addBindValue(QByteArray(image_data))
                    query.addBindValue(current_date)
                    query.addBindValue(current_date)

                    if query.exec():
                        QMessageBox.information(
                            self,
                            'Добавление',
                            'Изображение добавлено'
                        )
                    else:
                        QMessageBox.warning(
                            self,
                            'Ошибка',
                            'Не удалось добавить изображение'
                        )

if __name__ == '__main__':
    app = QApplication(sys.argv)

    if create_database():
        app.setStyleSheet('''
            QPushButton {
                border-radius: 15px;
                padding: 8px;
                background-color: #dce8fa;
            }

            QPushButton:hover {
                background-color: #c5daf7;
            }

            QTextEdit, QListWidget, QLineEdit {
                border-radius: 10px;
                padding: 6px;
            }
        ''')

        window = MainWindow()
        window.show()

        sys.exit(app.exec())

