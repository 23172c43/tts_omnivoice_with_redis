import os

def print_tree(startpath, exclude_dirs):
    print(f"📂 {os.path.basename(os.path.abspath(startpath))}/")
    for root, dirs, files in os.walk(startpath):
        # Lọc bỏ các thư mục không muốn hiển thị
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        level = root.replace(startpath, '').count(os.sep)
        indent = '│   ' * level
        
        # Bỏ qua thư mục gốc vì đã in ở trên
        if root != startpath:
            print(f"{indent}├── 📁 {os.path.basename(root)}/")
            
        subindent = '│   ' * (level + 1)
        for f in files:
            print(f"{subindent}├── 📄 {f}")

# Gọi hàm và điền các thư mục muốn ẩn (ví dụ model AI khổng lồ hoặc cache)
print_tree('.', exclude_dirs=['venv', '__pycache__', '.git', 'local_models'])