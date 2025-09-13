import sys, os, re
import pandas as pd
from math import floor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QPushButton, QMessageBox,
    QHBoxLayout, QLabel, QLineEdit, QComboBox, QFileDialog
)
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtCore import Qt, QMimeData
import qdarkstyle
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors

ML_PER_OZ = 29.5735

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())

def infer_bottle_size_oz(row) -> float:
    """
    Try to infer bottle size (in oz) from inventory columns.
    Priority:
      - bottle_size_oz (if present)
      - unit_size_ml (if present)
      - size_display (e.g., '750ml', '1L', '1.75L')
    Fallback: 25.36 oz (750ml)
    """
    # explicit bottle_size_oz
    if "bottle_size_oz" in row and pd.notna(row["bottle_size_oz"]):
        try:
            return float(row["bottle_size_oz"])
        except Exception:
            pass

    # numeric ml
    if "unit_size_ml" in row and pd.notna(row["unit_size_ml"]):
        try:
            return float(row["unit_size_ml"]) / ML_PER_OZ
        except Exception:
            pass

    # parse size_display
    if "size_display" in row and pd.notna(row["size_display"]):
        text = str(row["size_display"]).strip().lower().replace(" ", "")
        m = re.match(r"([\d\.]+)(ml|l|oz)$", text)
        if m:
            num = float(m.group(1))
            unit = m.group(2)
            if unit == "ml":
                return num / ML_PER_OZ
            elif unit == "l":
                return (num * 1000.0) / ML_PER_OZ
            else:
                return num
        # patterns like 6x750ml → per bottle size is 750ml
        m2 = re.match(r"\d+[x×]([\d\.]+)(ml|l|oz)$", text)
        if m2:
            num = float(m2.group(1))
            unit = m2.group(2)
            if unit == "ml":
                return num / ML_PER_OZ
            elif unit == "l":
                return (num * 1000.0) / ML_PER_OZ
            else:
                return num

    # fallback 750ml
    return 750.0 / ML_PER_OZ


class InventoryApp(QMainWindow):
    def __init__(self, csv_file):
        super().__init__()
        self.setWindowTitle("Inventory Counter")
        self.setGeometry(100, 100, 1150, 800)
        self.csv_file = csv_file

        # Load inventory
        self.df = pd.read_csv(csv_file)
        if "leftover_oz" not in self.df.columns:
            self.df["leftover_oz"] = 0.0  # track open bottle remainder

        # Build quick lookup indexes
        self.df["_norm_name"] = self.df["item_name"].apply(norm)

        # Load recipes
        self.recipes_path = "recipes.csv"
        try:
            self.recipes = pd.read_csv(self.recipes_path)
        except Exception:
            self.recipes = pd.DataFrame(columns=["cocktail","ingredient","amount_oz"])
        self.recipes["_norm_cocktail"] = self.recipes["cocktail"].apply(norm)
        self.recipes["_norm_ingredient"] = self.recipes["ingredient"].apply(norm)

        # Accept drag & drop (for sales files)
        self.setAcceptDrops(True)

        # === Summary Bar ===
        self.summary_bar = QHBoxLayout()
        self.total_label = QLabel()
        self.low_label = QLabel()
        self.category_label = QLabel()
        for lbl in [self.total_label, self.low_label, self.category_label]:
            lbl.setFont(QFont("Arial", 12, QFont.Bold))
            self.summary_bar.addWidget(lbl)
        self.update_summary()

        # === Search + Filter ===
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Search by name...")
        self.search_bar.textChanged.connect(self.apply_filters)

        self.category_filter = QComboBox()
        self.category_filter.addItem("All Categories")
        if "category" in self.df.columns:
            for cat in sorted(self.df["category"].dropna().unique()):
                self.category_filter.addItem(cat)
        self.category_filter.currentTextChanged.connect(self.apply_filters)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(self.search_bar)
        filter_layout.addWidget(self.category_filter)

        # === Table ===
        self.table = QTableWidget()
        self.table.setSortingEnabled(True)
        self.load_table()

        self.table.cellChanged.connect(self.cell_edited)

        # === Buttons ===
        self.save_button = QPushButton("💾 Save Changes")
        self.save_button.setStyleSheet("font-size: 14px; padding: 8px;")
        self.save_button.clicked.connect(self.save_changes)

        self.import_button = QPushButton("⬆ Import Sales (CSV/XLSX)")
        self.import_button.setStyleSheet("font-size: 14px; padding: 8px;")
        self.import_button.clicked.connect(self.import_sales_dialog)

        self.export_excel_button = QPushButton("📊 Export to Excel")
        self.export_excel_button.setStyleSheet("font-size: 14px; padding: 8px;")
        self.export_excel_button.clicked.connect(self.export_to_excel)

        self.export_pdf_button = QPushButton("📄 Export to PDF")
        self.export_pdf_button.setStyleSheet("font-size: 14px; padding: 8px;")
        self.export_pdf_button.clicked.connect(self.export_to_pdf)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.import_button)
        button_layout.addWidget(self.export_excel_button)
        button_layout.addWidget(self.export_pdf_button)

        # === Layout ===
        container = QWidget()
        layout = QVBoxLayout()
        layout.addLayout(self.summary_bar)
        layout.addLayout(filter_layout)
        layout.addWidget(self.table)
        layout.addLayout(button_layout)
        container.setLayout(layout)
        self.setCentralWidget(container)

    # ---------- UI & Table ----------
    def load_table(self, data=None):
        df_to_show = data if data is not None else self.df

        self.table.blockSignals(True)  # prevent cellChanged while filling
        self.table.setRowCount(len(df_to_show))
        self.table.setColumnCount(len(df_to_show.columns))
        self.table.setHorizontalHeaderLabels(df_to_show.columns)

        for i in range(len(df_to_show)):
            for j, col in enumerate(df_to_show.columns):
                value = "" if pd.isna(df_to_show.iloc[i, j]) else str(df_to_show.iloc[i, j])
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() | 0x2)  # editable
                self.table.setItem(i, j, item)

        self.apply_highlighting()
        self.table.resizeColumnsToContents()
        self.table.setAlternatingRowColors(True)
        self.table.blockSignals(False)

    def apply_highlighting(self):
        if "on_hand" in self.df.columns and "low_threshold" in self.df.columns:
            on_idx = self.df.columns.get_loc("on_hand")
            low_idx = self.df.columns.get_loc("low_threshold")
            for i in range(self.table.rowCount()):
                try:
                    stock = float(self.table.item(i, on_idx).text())
                    threshold = float(self.table.item(i, low_idx).text())
                    cell = self.table.item(i, on_idx)
                    if stock <= threshold:
                        cell.setBackground(QColor("#8B0000"))
                        cell.setForeground(QColor("white"))
                    else:
                        cell.setBackground(QColor("transparent"))
                        cell.setForeground(QColor("white"))
                except Exception:
                    pass

    def apply_filters(self):
        search_term = self.search_bar.text().lower()
        category_filter = self.category_filter.currentText()

        filtered = self.df.copy()
        if search_term:
            filtered = filtered[filtered["item_name"].str.lower().str.contains(search_term, na=False)]
        if category_filter != "All Categories" and "category" in filtered.columns:
            filtered = filtered[filtered["category"] == category_filter]
        self.load_table(filtered)

    def cell_edited(self, row, col):
        # Update df to match edits in current view
        try:
            new_value = self.table.item(row, col).text()
        except Exception:
            return

        # Map edited row back to underlying df row by item_name (simplest stable key here)
        item_col_idx = self.table.horizontalHeaderItem(0).text()  # assumes 'item_name' is first col
        try:
            current_item = self.table.item(row, self.df.columns.get_loc("item_name")).text()
            mask = self.df["item_name"] == current_item
            if mask.any():
                real_row = self.df.index[mask][0]
                self.df.iat[real_row, col] = new_value
        except Exception:
            pass

        self.apply_highlighting()
        self.update_summary()

    def save_changes(self):
        self.df.to_csv(self.csv_file, index=False)
        QMessageBox.information(self, "Saved", f"Changes saved to {self.csv_file}")

    def export_to_excel(self):
        excel_file = self.csv_file.replace(".csv", "_report.xlsx")
        self.df.to_excel(excel_file, index=False)
        QMessageBox.information(self, "Exported", f"Inventory exported to {excel_file}")

    def export_to_pdf(self):
        pdf_file = self.csv_file.replace(".csv", "_report.pdf")
        doc = SimpleDocTemplate(pdf_file, pagesize=letter)
        data = [self.df.columns.tolist()] + self.df.values.tolist()
        table = Table(data)
        style = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ])
        table.setStyle(style)
        doc.build([table])
        QMessageBox.information(self, "Exported", f"Inventory exported to {pdf_file}")

    def update_summary(self):
        total_items = len(self.df)
        try:
            low_stock = (self.df["on_hand"].astype(float) <= self.df["low_threshold"].astype(float)).sum()
        except Exception:
            low_stock = 0
        categories = self.df["category"].nunique() if "category" in self.df.columns else 0
        self.total_label.setText(f"✅ Total Items: {total_items}")
        self.low_label.setText(f"📉 Low Stock: {low_stock}")
        self.category_label.setText(f"🍶 Categories: {categories}")

    # ---------- Sales Import ----------
    def import_sales_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Sales File", "", "CSV/Excel (*.csv *.xlsx)")
        if path:
            self.process_sales_file(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith((".csv", ".xlsx")):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".csv", ".xlsx")):
                self.process_sales_file(path)

    def read_sales(self, path: str) -> pd.DataFrame:
        if path.lower().endswith(".csv"):
            df = pd.read_csv(path)
        else:
            df = pd.read_excel(path)

        # Try to normalize common column names: cocktail/menu item & quantity
        cols = {c.lower().strip(): c for c in df.columns}
        name_col = None
        qty_col = None
        for cand in ["item", "menu item", "menu_item", "name", "cocktail", "product"]:
            if cand in cols:
                name_col = cols[cand]; break
        for cand in ["qty", "quantity", "count", "sold", "units"]:
            if cand in cols:
                qty_col = cols[cand]; break

        if not name_col or not qty_col:
            raise ValueError("Sales file must have columns for cocktail name and quantity (e.g., 'Item' + 'Quantity').")

        out = df[[name_col, qty_col]].copy()
        out.columns = ["cocktail", "quantity"]
        out = out.groupby("cocktail", as_index=False)["quantity"].sum()
        return out

    def process_sales_file(self, path: str):
        try:
            sales = self.read_sales(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read sales file:\n{e}")
            return

        # Reduce to only cocktails we have recipes for (spirits only)
        sales["_norm_cocktail"] = sales["cocktail"].apply(norm)

        missing_cocktails = []
        missing_ingredients = []
        total_deductions = {}  # ingredient -> total_oz

        for _, row in sales.iterrows():
            c_norm = row["_norm_cocktail"]
            qty = float(row["quantity"])

            rcp_rows = self.recipes[self.recipes["_norm_cocktail"] == c_norm]
            if rcp_rows.empty:
                missing_cocktails.append(row["cocktail"])
                continue

            # only spirits/liqueurs: the recipes already contain just liquor entries
            for _, r in rcp_rows.iterrows():
                ing = r["ingredient"]
                ing_norm = r["_norm_ingredient"]
                amt_oz = float(r["amount_oz"])
                total_deductions[ing] = total_deductions.get(ing, 0.0) + amt_oz * qty

        # Apply deductions to inventory
        not_in_inventory = []
        for ing, oz_needed in total_deductions.items():
            mask = self.df["_norm_name"] == norm(ing)
            if not mask.any():
                not_in_inventory.append(ing)
                continue

            idx = self.df.index[mask][0]
            bottle_oz = infer_bottle_size_oz(self.df.loc[idx])

            # compute total remaining ounces BEFORE deduction
            try:
                on_hand = float(self.df.at[idx, "on_hand"])
            except Exception:
                on_hand = 0.0
            try:
                leftover = float(self.df.at[idx, "leftover_oz"])
            except Exception:
                leftover = 0.0

            total_oz = on_hand * bottle_oz + leftover
            total_oz = max(0.0, total_oz - oz_needed)

            # recompute on_hand / leftover
            new_on_hand = floor(total_oz / bottle_oz)
            new_leftover = total_oz - (new_on_hand * bottle_oz)

            self.df.at[idx, "on_hand"] = new_on_hand
            self.df.at[idx, "leftover_oz"] = round(new_leftover, 2)  # keep tidy decimals

        # Refresh UI + summary
        self.update_summary()
        self.load_table()

        # Build summary message
        msg = []
        if total_deductions:
            msg.append("Deductions applied:")
            for k, v in total_deductions.items():
                msg.append(f"  • {k}: {round(v,2)} oz")
        if missing_cocktails:
            msg.append("\nNo recipe found for cocktails:")
            for c in sorted(set(missing_cocktails)):
                msg.append(f"  • {c}")
        if not_in_inventory:
            msg.append("\nIngredients not found in inventory:")
            for i in sorted(set(not_in_inventory)):
                msg.append(f"  • {i}")

        if not msg:
            msg = ["No matching cocktails or ingredients found in this sales file."]
        QMessageBox.information(self, "Sales Imported", "\n".join(msg))
if __name__ == "__main__":
    print("Starting Inventory App...")  # debug message
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())  # dark modern look
    window = InventoryApp("inventory.csv")  # make sure your file is named correctly
    window.show()
    sys.exit(app.exec_())
