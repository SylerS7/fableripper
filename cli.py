import sys
import argparse
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.table import Table

# Ensure console supports utf-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import DEFAULT_CONCURRENCY
from engine import NovelPipeline

console = Console()

def print_banner():
    console.print(
        Panel.fit(
            "[bold cyan]Novel to EPUB Downloader[/bold cyan]\n"
            "[dim]Universal Multi-Platform Novel Scraper & E-Book Converter[/dim]",
            border_style="cyan"
        )
    )

def main():
    parser = argparse.ArgumentParser(
        description="Fetch novel chapter contents from any web link and convert them into EPUB, TXT, or Markdown."
    )
    parser.add_argument(
        "url",
        nargs="?",
        default="https://www.wuxiaspot.com/novel/battle-through-the-heavens.html",
        help="URL of the novel (supports WuxiaSpot, Royal Road, NovelFull, or any web novel site)"
    )
    parser.add_argument(
        "--start",
        "-s",
        type=int,
        default=None,
        help="Start chapter number (inclusive). Omit to start from Chapter 1."
    )
    parser.add_argument(
        "--end",
        "-e",
        type=int,
        default=None,
        help="End chapter number (inclusive). Omit to download until the last chapter."
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["epub", "txt", "md"],
        default="epub",
        help="Export format: epub (default), txt, or md (markdown)"
    )
    parser.add_argument(
        "--split",
        "-v",
        type=int,
        default=None,
        help="Split chapters into multiple volumes (e.g. --split 200 for 200 chapters per volume)"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Custom output file path (e.g. output/BTTH.epub)"
    )
    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Number of concurrent download threads (default: {DEFAULT_CONCURRENCY})"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore cached chapters and re-download fresh content."
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Display novel info and chapter list without downloading chapters."
    )

    args = parser.parse_args()

    print_banner()

    console.print(f"[bold green]Target URL:[/bold green] {args.url}")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task_id = progress.add_task("[yellow]Initializing...", total=100)

        def progress_callback(msg: str, percent: float):
            progress.update(task_id, description=f"[cyan]{msg}[/cyan]", completed=int(percent * 100))

        pipeline = NovelPipeline(
            url=args.url,
            concurrency=args.concurrency,
            use_cache=not args.no_cache,
            on_progress=progress_callback
        )

        if args.info:
            metadata = pipeline.get_novel_info()
            progress.update(task_id, description="[green]Done fetching info[/green]", completed=100)
            
            table = Table(title="Novel Information")
            table.add_column("Property", style="bold cyan")
            table.add_column("Value")
            table.add_row("Platform", metadata.platform)
            table.add_row("Title", metadata.title)
            table.add_row("Author", metadata.author)
            table.add_row("Slug", metadata.slug)
            table.add_row("Categories", ", ".join(metadata.categories) if metadata.categories else "General")
            table.add_row("Total Chapters", str(len(metadata.chapters)))
            if metadata.chapters:
                table.add_row("First Chapter", f"Ch {metadata.chapters[0].number}: {metadata.chapters[0].title}")
                table.add_row("Last Chapter", f"Ch {metadata.chapters[-1].number}: {metadata.chapters[-1].title}")
            table.add_row("Cover URL", metadata.cover_url or "None")
            console.print(table)
            return

        try:
            res = pipeline.run(
                start_chapter=args.start,
                end_chapter=args.end,
                output_file=args.output,
                export_format=args.format,
                split_volumes=args.split
            )
            progress.update(task_id, description="[bold green]Export Complete![/bold green]", completed=100)
            
            if isinstance(res, list):
                files_str = "\n".join(f"- {p.resolve()}" for p in res)
                console.print(
                    Panel(
                        f"[bold green]Successfully generated {len(res)} volumes![/bold green]\n\n"
                        f"{files_str}",
                        border_style="green",
                        title="Success"
                    )
                )
            else:
                size_mb = res.stat().st_size / (1024 * 1024)
                console.print(
                    Panel(
                        f"[bold green]{args.format.upper()} successfully generated![/bold green]\n\n"
                        f"[bold]File:[/bold] {res.resolve()}\n"
                        f"[bold]Size:[/bold] {size_mb:.2f} MB\n"
                        f"[dim]Ready for Kindle, Apple Books, Kobo, or Calibre.[/dim]",
                        border_style="green",
                        title="Success"
                    )
                )
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
