# ModMaker Architecture - MVVM Pattern

## โครงสร้างโปรเจค

```
ModMakerAlpha/
├── app.py                      # จุดเริ่มต้นของแอปพลิเคชัน
│
├── models/                     # Model Layer - Data & Business Logic
│   ├── __init__.py
│   ├── asset_model.py         # AssetInfo, ResultStatus, PreviewResult, etc.
│   └── core_model.py          # ModMakerCore - โหลดและจัดการ Unity bundles
│
├── views/                      # View Layer - UI Components
│   ├── __init__.py
│   ├── main_window.py         # หน้าต่างหลัก (compose ทุก components)
│   ├── asset_table_widget.py  # ตารางแสดงรายการ assets
│   └── preview_panel_widget.py # แสดงตัวอย่าง assets
│
├── viewmodels/                 # ViewModel Layer - Presentation Logic
│   ├── __init__.py
│   └── main_viewmodel.py      # จัดการ state และ business logic
│
├── services/                   # Services - Background Workers
│   ├── __init__.py
│   ├── loader_worker.py       # โหลดไฟล์ใน background thread
│   ├── edit_worker.py         # แก้ไข asset ใน background thread
│   └── logging_handler.py     # ส่ง logs ไปแสดงใน UI
│
├── utilities/                  # Utilities - Helper Classes
│   ├── __init__.py
│   ├── single_instance.py     # จำกัดให้เปิดได้แค่ instance เดียว
│   └── file_drop_widget.py    # รองรับ drag & drop files
│
├── photoviewer.py             # PhotoViewer component (เดิม)
└── custom_filter_header.py   # FilterHeader component (เดิม)
```

## MVVM Pattern

### Model Layer (`models/`)
- **หน้าที่**: จัดเก็บข้อมูลและ business logic
- **ไฟล์**:
  - `asset_model.py`: โครงสร้างข้อมูล (AssetInfo, Result types)
  - `core_model.py`: Core logic (ModMakerCore)
- **ไม่ควร**: มี dependencies กับ UI หรือ PySide6 widgets

### View Layer (`views/`)
- **หน้าที่**: แสดงผล UI และรับ user input
- **ไฟล์**:
  - `main_window.py`: หน้าต่างหลัก ประกอบจาก components ต่างๆ
  - `asset_table_widget.py`: แสดงตารางรายการ assets
  - `preview_panel_widget.py`: แสดงตัวอย่าง assets
- **ควร**: เป็น "dumb components" เน้นแสดงผลเท่านั้น
- **ไม่ควร**: มี business logic ซับซ้อน

### ViewModel Layer (`viewmodels/`)
- **หน้าที่**: เชื่อมระหว่าง Model และ View
- **ไฟล์**:
  - `main_viewmodel.py`: จัดการ state, business logic, data binding
- **ควร**: 
  - ใช้ Qt Signals เพื่อ notify Views
  - ไม่มี references ตรงไปยัง widgets
  - เป็น testable (ไม่ต้องมี UI)

### Services (`services/`)
- **หน้าที่**: Background workers และ handlers
- **ไฟล์**:
  - `loader_worker.py`: โหลดไฟล์แบบ async
  - `edit_worker.py`: แก้ไขข้อมูลแบบ async
  - `logging_handler.py`: จัดการ logging ให้ UI

### Utilities (`utilities/`)
- **หน้าที่**: Helper classes ที่ใช้ทั่วโครงการ
- **ไฟล์**:
  - `single_instance.py`: ป้องกันเปิดหลาย instance
  - `file_drop_widget.py`: Widget สำหรับ drag & drop

## การรันแอปพลิเคชัน

```bash
# ใช้ uv (แนะนำ)
uv run app.py

# หรือใช้ python ธรรมดา
python app.py
```

## ข้อดีของสถาปัตยกรรมใหม่

1. **Separation of Concerns** ✅
   - Model, View, ViewModel แยกชัดเจน
   - แต่ละ layer มีหน้าที่เฉพาะ

2. **Testability** ✅
   - ViewModel testable โดยไม่ต้องมี UI
   - Models testable แยกอิสระ

3. **Maintainability** ✅
   - ไฟล์เล็กลง อ่านง่าย
   - โครงสร้างชัดเจน หาเจอง่าย

4. **Reusability** ✅
   - Components นำกลับมาใช้ใหม่ได้
   - Views ใช้ในหลาย contexts ได้

5. **SOLID Principles** ✅
   - Single Responsibility: แต่ละ class มีหน้าที่เดียว
   - Open/Closed: ขยายได้โดยไม่แก้ของเดิม
   - Dependency Inversion: พึ่งพา abstractions

## Data Flow

```
User Action
    ↓
View (UI Component)
    ↓ (emit signal)
ViewModel (Business Logic)
    ↓ (use)
Model (Data/Core Logic)
    ↓ (return result)
ViewModel
    ↓ (emit signal)
View (Update UI)
```

## การเพิ่มฟีเจอร์ใหม่

1. **เพิ่ม Model**: สร้างไฟล์ใน `models/`
2. **เพิ่ม View**: สร้าง widget ใน `views/`
3. **เพิ่ม Logic**: อัปเดต `viewmodels/main_viewmodel.py`
4. **Wire Up**: เชื่อม signals ใน `views/main_window.py`

## หมายเหตุ

- ไฟล์ `photoviewer.py` และ `custom_filter_header.py` ยังอยู่ใน root เพราะเป็น standalone components
- ใช้ Python 3.10+ (เพราะใช้ type hints แบบ `list[str]`)

