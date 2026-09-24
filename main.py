import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="Novel to EPUB Tool")
    parser.add_argument("--web", action="store_true", help="Launch the local Web GUI interface")
    parser.add_argument("--port", type=int, default=5000, help="Port for the Web GUI (default: 5000)")
    
    # If arguments start with --web, run the web application
    if len(sys.argv) > 1 and ("--web" in sys.argv or "-w" in sys.argv):
        from web_app import app
        parsed, _ = parser.parse_known_args()
        print(f"\n🚀 Launching Novel to EPUB Web Interface at http://127.0.0.1:{parsed.port}")
        app.run(host="127.0.0.1", port=parsed.port)
    else:
        from cli import main as cli_main
        cli_main()

if __name__ == "__main__":
    main()
