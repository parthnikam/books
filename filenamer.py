import fnmatch
import os

# get all file names in the folders and subfolders
# organize them in a nested list
# update readme file table

def load_gitignore_patterns(directory):
    patterns = []
    gitignore_path = os.path.join(directory, '.gitignore')
    if not os.path.isfile(gitignore_path):
        return patterns

    with open(gitignore_path, 'r', encoding='utf-8') as f:
        for line in f:
            pattern = line.strip()
            if not pattern or pattern.startswith('#'):
                continue
            patterns.append(pattern)
    return patterns


def matches_ignore_pattern(rel_path, patterns, is_dir=False):
    normalized = rel_path.replace(os.sep, '/')
    for pattern in patterns:
        if not pattern or pattern.startswith('#'):
            continue
        pat = pattern.rstrip('/')
        if pattern.endswith('/'):
            if normalized == pat or normalized.startswith(pat + '/'):
                return True
        elif pattern.startswith('/'):
            pat = pat[1:]
            if fnmatch.fnmatch(normalized, pat):
                return True
        else:
            if fnmatch.fnmatch(normalized, pat) or fnmatch.fnmatch(os.path.basename(normalized), pat):
                return True
    return False


def crawl_files(directory):
    files_list = []
    directory = os.path.abspath(directory)
    ignore_patterns = load_gitignore_patterns(directory)

    for root, dirs, files in os.walk(directory):
        rel_root = os.path.relpath(root, directory)
        normalized_root = '' if rel_root == '.' else rel_root.replace(os.sep, '/')

        dirs[:] = [d for d in dirs if d not in ['.git', '.vscode']]
        dirs[:] = [d for d in dirs if not matches_ignore_pattern(os.path.join(normalized_root, d).lstrip('/'), ignore_patterns, is_dir=True)]

        for file in files:
            if file in ['desktop.ini', 'filenamer.py', 'README.md', '.gitignore']:
                continue

            file_rel = os.path.join(normalized_root, file).lstrip('/')
            if matches_ignore_pattern(file_rel, ignore_patterns, is_dir=False):
                continue

            rel_path = os.path.relpath(root, directory)
            if rel_path == '.':
                tag = 'Root'
            else:
                path_parts = rel_path.split(os.sep)
                tag = path_parts[-1] if path_parts else 'Root'
            original_file = file
            display_file = file.replace('_', ' ')
            file_rel_path = os.path.join(rel_path, original_file) if rel_path != '.' else original_file
            files_list.append((display_file, file_rel_path, tag))
    return files_list


def generate_md_table(files_list):
    md = "# Books Table\n\n| Book | Tag |\n|-----------|------|\n"
    for fname, path, tag in sorted(files_list):
        md += f"| {fname} | {tag} |\n"
    return md


if __name__ == "__main__":
    directory = os.path.dirname(os.path.abspath(__file__))
    files = crawl_files(directory)
    table = generate_md_table(files)
    with open(os.path.join(directory, 'BOOKS.md'), 'w', encoding='utf-8') as f:
        f.write(table)
