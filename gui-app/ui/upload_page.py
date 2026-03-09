from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton,
    QFileDialog, QTextEdit
)

# from utils.data_loader import load_file
from src.services.assessment_service import store_microbiome_upload


class UploadPage(QWidget):

    def __init__(self, project_id):
        super().__init__()

        self.project_id = project_id
        self.file_path = None

        layout = QVBoxLayout()

        self.upload_btn = QPushButton("Upload Microbiome File")
        self.upload_btn.clicked.connect(self.select_file)

        self.save_btn = QPushButton("Save to Database")
        self.save_btn.clicked.connect(self.save_microbiome)

        self.output = QTextEdit()

        layout.addWidget(self.upload_btn)
        layout.addWidget(self.save_btn)
        layout.addWidget(self.output)

        self.setLayout(layout)

        self.taxa_dict = None

    # ---------------------------
    # Step 1: Select file
    # ---------------------------

    def select_file(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Microbiome File",
            "",
            "Data Files (*.csv *.tsv *.json)"
        )

        if not path:
            return

        self.file_path = path

        result = load_file(path)

        self.output.append("File Loaded\n")
        self.output.append(result["summary"])

        # Convert to taxa proportions if possible
        self.taxa_dict = self._extract_taxa(result)

    # ---------------------------
    # Step 2: Convert to taxa dict
    # ---------------------------

    def _extract_taxa(self, result):

        rows = result["raw_data"]

        if isinstance(rows, list) and rows:
            row = rows[0]

            taxa = {}
            total = 0

            for k, v in row.items():
                try:
                    val = float(v)
                    taxa[k] = val
                    total += val
                except:
                    pass

            if total > 0:
                taxa = {k: v / total for k, v in taxa.items()}

            return taxa

        if isinstance(rows, dict):
            total = sum(rows.values())
            return {k: v / total for k, v in rows.items()}

        return {}

    # ---------------------------
    # Step 3: Store in DB
    # ---------------------------

    def save_microbiome(self):

        if not self.taxa_dict:
            self.output.append("No taxa data found.")
            return

        try:

            result = store_microbiome_upload(
                project_id=self.project_id,
                file_path=self.file_path,
                taxa=self.taxa_dict
            )

            self.output.append("\nSaved to Database:")
            self.output.append(str(result))

        except Exception as e:
            self.output.append(f"Error: {str(e)}")