"""
@Author: 幻璃次元日报
@Description: 角色批量导入工具，支持CSV/Excel
@Usage: python batch_import.py --input characters.csv [--dry-run]
@Version: 1.0.0
"""

import json
import csv
import argparse
import sys
from pathlib import Path
from typing import List, Dict, Tuple

# 可选：支持Excel
HAS_OPENPYXL = False
try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    pass


class BatchImporter:
    """批量导入器"""

    def __init__(self, plugin_dir: Path, dry_run: bool = False):
        self.plugin_dir = plugin_dir
        self.data_dir = plugin_dir / "data"
        self.assets_dir = plugin_dir / "assets"
        self.dry_run = dry_run
        self.ip_index = self._load_ip_index()
        self.stats = {"created": 0, "skipped": 0, "errors": 0, "ips_updated": set()}

    def import_from_csv(self, csv_path: str) -> Tuple[int, int, int]:
        csv_file = Path(csv_path)
        if not csv_file.exists():
            print(f"❌ 文件不存在: {csv_file}")
            return 0, 0, 0

        characters = self._parse_csv(csv_file)
        return self._process_characters(characters)

    def import_from_excel(self, excel_path: str, sheet_index: int = 0) -> Tuple[int, int, int]:
        if not HAS_OPENPYXL:
            print("❌ 未安装 openpyxl。请执行: pip install openpyxl")
            return 0, 0, 0

        excel_file = Path(excel_path)
        if not excel_file.exists():
            print(f"❌ 文件不存在: {excel_file}")
            return 0, 0, 0

        characters = self._parse_excel(excel_file, sheet_index)
        return self._process_characters(characters)

    def _parse_csv(self, csv_path: Path) -> List[Dict]:
        characters = []
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                char = self._clean_row(row)
                if char:
                    characters.append(char)
        return characters

    def _parse_excel(self, excel_path: Path, sheet_index: int) -> List[Dict]:
        characters = []
        wb = openpyxl.load_workbook(excel_path)
        sheet = wb.worksheets[sheet_index]
        headers = [cell.value for cell in sheet[1]]

        for row in sheet.iter_rows(min_row=2, values_only=True):
            row_dict = dict(zip(headers, row))
            char = self._clean_row(row_dict)
            if char:
                characters.append(char)
        return characters

    def _clean_row(self, row: Dict) -> Dict:
        required = ["ip", "name", "work"]
        for field in required:
            if not row.get(field):
                print(f"⚠️ 跳过: 缺少必填字段 '{field}' - {row}")
                self.stats["errors"] += 1
                return {}

        tags = row.get("tags", "")
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        return {
            "ip": str(row["ip"]).strip().lower(),
            "name": str(row["name"]).strip(),
            "name_en": str(row.get("name_en", "")).strip(),
            "work": str(row["work"]).strip(),
            "tags": tags,
            "quote": str(row.get("quote", "")).strip(),
            "description": str(row.get("description", "")).strip()
        }

    def _process_characters(self, characters: List[Dict]) -> Tuple[int, int, int]:
        ip_groups: Dict[str, List[Dict]] = {}
        for char in characters:
            ip = char["ip"]
            if ip not in ip_groups:
                ip_groups[ip] = []
            ip_groups[ip].append(char)

        valid_ips = {ip["id"] for ip in self.ip_index["ips"]}
        for ip in list(ip_groups.keys()):
            if ip not in valid_ips:
                print(f"⚠️ IP '{ip}' 不在索引中，将自动添加")
                self._add_new_ip(ip)

        for ip, chars in ip_groups.items():
            self._process_ip_group(ip, chars)

        if not self.dry_run and self.stats["ips_updated"]:
            self._save_ip_index()

        return self.stats["created"], self.stats["skipped"], self.stats["errors"]

    def _process_ip_group(self, ip: str, characters: List[Dict]):
        ip_folder = self.data_dir / "characters" / ip
        asset_folder = self.assets_dir / "characters" / ip

        if not self.dry_run:
            ip_folder.mkdir(parents=True, exist_ok=True)
            asset_folder.mkdir(parents=True, exist_ok=True)

        existing_files = list(ip_folder.glob("*.json")) if ip_folder.exists() else []
        next_id = len(existing_files) + 1

        for char in characters:
            local_id = f"{next_id:03d}"
            global_id = f"{ip}_{local_id}"

            existing = list(ip_folder.glob(f"*_{char['name']}.json"))
            if existing:
                print(f"⏭️ 跳过已存在: {char['name']} ({ip})")
                self.stats["skipped"] += 1
                continue

            char_data = {
                "ip": ip,
                "local_id": local_id,
                "global_id": global_id,
                "name": char["name"],
                "name_en": char["name_en"],
                "work": char["work"],
                "tags": char["tags"],
                "quote": char["quote"],
                "description": char["description"],
                "image_file": f"{local_id}.png"
            }

            filename = f"{local_id}_{char['name']}.json"
            filepath = ip_folder / filename

            if self.dry_run:
                print(f"[DRY-RUN] 将创建: {filepath}")
            else:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(char_data, f, ensure_ascii=False, indent=2)
                print(f"✅ 创建: {filename}")

            self.stats["created"] += 1
            next_id += 1

        self.stats["ips_updated"].add(ip)

    def _load_ip_index(self) -> Dict:
        with open(self.data_dir / "ip_index.json", "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_ip_index(self):
        for ip in self.ip_index["ips"]:
            ip_folder = self.data_dir / "characters" / ip["folder"]
            if ip_folder.exists():
                count = len(list(ip_folder.glob("*.json")))
                ip["total_characters"] = count

        with open(self.data_dir / "ip_index.json", "w", encoding="utf-8") as f:
            json.dump(self.ip_index, f, ensure_ascii=False, indent=2)
        print("✅ IP索引已更新")

    def _add_new_ip(self, ip_id: str):
        new_ip = {
            "id": ip_id,
            "name": ip_id.upper(),
            "name_en": ip_id.upper(),
            "folder": ip_id,
            "default_weight": 1,
            "description": f"自动添加的IP: {ip_id}",
            "total_characters": 0
        }
        self.ip_index["ips"].append(new_ip)

        if not self.dry_run:
            (self.data_dir / "characters" / ip_id).mkdir(parents=True, exist_ok=True)
            (self.assets_dir / "characters" / ip_id).mkdir(parents=True, exist_ok=True)

        print(f"✅ 已添加新IP: {ip_id}")


def main():
    parser = argparse.ArgumentParser(description="角色批量导入工具")
    parser.add_argument("--input", "-i", required=True, help="输入文件路径 (CSV或Excel)")
    parser.add_argument("--sheet", "-s", type=int, default=0, help="Excel工作表索引")
    parser.add_argument("--dry-run", "-d", action="store_true", help="试运行")
    parser.add_argument("--plugin-dir", "-p", default=".", help="插件目录路径")

    args = parser.parse_args()

    plugin_dir = Path(args.plugin_dir).resolve()
    importer = BatchImporter(plugin_dir, dry_run=args.dry_run)

    input_path = Path(args.input)
    suffix = input_path.suffix.lower()

    if suffix == ".csv":
        created, skipped, errors = importer.import_from_csv(str(input_path))
    elif suffix in [".xlsx", ".xls"]:
        created, skipped, errors = importer.import_from_excel(str(input_path), args.sheet)
    else:
        print(f"❌ 不支持的文件格式: {suffix}")
        sys.exit(1)

    print("\n" + "=" * 50)
    print("导入完成!")
    print(f"  成功创建: {created}")
    print(f"  跳过(已存在): {skipped}")
    print(f"  错误: {errors}")
    print("=" * 50)

    if args.dry_run:
        print("\n⚠️ 本次为试运行，未实际写入文件。去掉 --dry-run 正式执行。")


if __name__ == "__main__":
    main()
