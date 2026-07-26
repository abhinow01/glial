"""
CLI entry point. main.js calls this — nothing else should.
"""
import sys
from indexer  import index_folder
from searcher import search

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: index_search.py index|search ...")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == 'index':
        # args: index <folder> <frames_dir> <db_path> [ffmpeg_path]
        index_folder(
            folder_path  = sys.argv[2],
            db_path      = sys.argv[3],
            frames_cache = sys.argv[4],
            ffmpeg_path  = sys.argv[5] if len(sys.argv) > 5 else 'ffmpeg'
        )

    elif mode == 'search':
        # args: search <db_path> "query" [top_k]
        search(
            db_path = sys.argv[2],
            query   = sys.argv[3],
            top_k   = int(sys.argv[4]) if len(sys.argv) > 4 else 10
        )

    else:
        print(f"Unknown mode '{mode}'. Use 'index' or 'search'.")
        sys.exit(1)