import sys

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QDialog
from PyQt6.QtWidgets import  QTextEdit, QLabel, QListWidget, QListWidgetItem, QMenu, QFileDialog, QMessageBox
from PyQt6.QtWidgets import QLineEdit, QInputDialog
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QDir, QFile, QFileInfo, QIODevice, QByteArray, QStandardPaths
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
        CREATE TABLE IF NOT EXISTS texts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            content TEXT,
            date_added TEXT
        )
    ''')

    query.exec('''
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            content BLOB,
            date_added TEXT
        )
    ''')

    return True

class TextEditor(QDialog):
    def __init__(self, record_id=None):
        super().__init__()

        self.record_id = record_id
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

        if self.record_id:
            query.prepare(
                'UPDATE texts SET name = ?, content = ? WHERE id = ?'
            )
            query.addBindValue(name)
            query.addBindValue(content)
            query.addBindValue(self.record_id)
        else:
            query.prepare(
                'INSERT INTO texts (name, content, date_added) VALUES (?, ?, ?)'
            )
            query.addBindValue(name)
            query.addBindValue(content)
            query.addBindValue(
                QDateTime.currentDateTime().toString(Qt.DateFormat.ISODate)
            )

        if query.exec():
            if not self.record_id:
                self.record_id = int(query.lastInsertId())

            QMessageBox.information(self, 'Сохранение', 'Текст сохранён')
        else:
            QMessageBox.warning(self, 'Ошибка', 'Не удалось сохранить текст')

class FilesWindow(QDialog):
    def __init__(self, title, is_text, sort_mode):
        super().__init__()

        self.is_text = is_text
        self.sort_mode = sort_mode
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
        layout.addWidget(open_button)
        layout.addWidget(delete_button)
        layout.addWidget(close_button)
        self.setLayout(layout)
        self.update_list()

    def update_list(self):
        self.files_list.clear()
        search_text = self.search.text().lower()
        query = QSqlQuery(database)

        if self.is_text:
            if self.sort_mode == 'size':
                sorting = 'LENGTH(content)'
            elif self.sort_mode == 'date':
                sorting = 'date_added'
            else:
                sorting = 'name COLLATE NOCASE'
            query.exec(
                'SELECT id, name FROM texts ORDER BY ' + sorting
            )
        else:
            if self.sort_mode == 'date':
                sorting = 'date_added'
            else:
                sorting = 'name COLLATE NOCASE'

            query.exec(
                'SELECT id, name FROM images ORDER BY ' + sorting
            )

        while query.next():
            record_id = query.value(0)
            name = query.value(1)
            if search_text in name.lower():
                item = QListWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, record_id)
                self.files_list.addItem(item)

    def open_file(self, item=None):
        if item is None:
            item = self.files_list.currentItem()
        if item:
            record_id = item.data(Qt.ItemDataRole.UserRole)
            if self.is_text:
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
                'Удалить выбранный файл?'
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
        window = FilesWindow(
            'Мои файлы (txt)',
            True,
            self.text_sort
        )
        window.exec()

    def open_image_files(self):
        window = FilesWindow(
            'Мои файлы (изображения)',
            False,
            self.image_sort
        )
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
                    query.prepare(
                        'INSERT INTO images (name, content, date_added) VALUES (?, ?, ?)'
                    )
                    query.addBindValue(name.strip())
                    query.addBindValue(QByteArray(image_data))
                    query.addBindValue(
                        QDateTime.currentDateTime().toString(Qt.DateFormat.ISODate)
                    )

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

    from PyQt6.QtCore import QDateTime

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