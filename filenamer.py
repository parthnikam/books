import os

# get all file names in the folders and subfolders 
# organize them in a nested list
# update readme file table

def crawl_files(directory):
    files_list = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            # Skip certain files like desktop.ini or the script itself
            if file in ['desktop.ini', 'filenamer.py', 'README.md', '.gitignore']:
                continue
            # Get relative path from directory
            rel_path = os.path.relpath(root, directory)
            # Tag is the immediate parent folder
            if rel_path == '.':
                tag = 'Root'
            else:
                # Split the path and take the last component
                path_parts = rel_path.split(os.sep)
                tag = path_parts[-1] if path_parts else 'Root'
            # Keep original file name for path
            original_file = file
            # Display file name with spaces instead of underscores
            display_file = file.replace('_', ' ')
            # Relative path to file using original name
            file_rel_path = os.path.join(rel_path, original_file) if rel_path != '.' else original_file
            files_list.append((display_file, file_rel_path, tag))
    return files_list

def generate_md_table(files_list):
    md = "# Books Table\n\n| Book | Tag |\n|-----------|------|\n"
    for fname, path, tag in sorted(files_list):
        md += f"| {fname} | {tag} |\n"
    return md

if __name__ == "__main__":
    directory = "C:/Users/108pa/Parth/Books"
    files = crawl_files(directory)
    table = generate_md_table(files)
    with open("BOOKS.md", "w") as f:
        f.write(table)