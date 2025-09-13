#  Avintory – Bar & Inventory Management  

Avintory is a lightweight system for managing **restaurant/bar inventory, recipes, and menus**.  
It’s designed to track stock, analyze costs, and provide easy reference for staff training and beverage program development.  

---

##  Project Structure  
```
Avintory/
│
├── app.py                # Main application logic
├── inventory.csv         # Master inventory list (stock, pricing, vendors)
├── recipes.csv           # Cocktail/recipe database
├── utils/
│   ├── adjuster.py       # Utility for adjusting recipe measurements
│   └── parser.py         # Utility for parsing inventory/recipes
└── README.md             # This file
```

---

##  Features  
-  Track **inventory** with CSV import/export  
-  Store & adjust **cocktail/food recipes**  
-  Link recipes with inventory for cost analysis  
-  Training docs (pairings, tasting notes) can be added for staff  
-  Built in **Python**, simple and extendable  

---

##  Requirements  
- Python 3.9+  
- Pandas (for CSV handling)  

Install dependencies:  
```bash
pip install pandas
```

---

## ▶ Usage  
1. Clone the repo:  
   ```bash
   git clone https://github.com/NetJumper/Avintory.git
   cd Avintory
   ```

2. Run the app:  
   ```bash
   python app.py
   ```

3. Update inventory in `inventory.csv` and recipes in `recipes.csv`.  

---

##  Data Files  
- **inventory.csv** → contains all current stock, costs, and vendor details.  
- **recipes.csv** → defines cocktail/food recipes (with ingredients, measures, glassware, garnish).  

---

##  Future Additions  
- Staff **cheat sheets** with tasting notes & food pairings  
- PDF menu exports for guests  
- POS integration  

---

##  Author  
Developed by **Jose Iriarte** for **Tabe Asian Fusion**’s beverage program.  

