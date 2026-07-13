import typer
from rich.console import Console
from rich.table import Table

from maref.obs import get_obs_level, get_obs_show, get_obs_status  # type: ignore[attr-defined]

app = typer.Typer()
console = Console()

def _fmt_size(size: int) -> str:
    try:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f'{size:.1f} {unit}'
            size /= 1024  # type: ignore[assignment]
        return f'{size:.1f} TB'
    except Exception:
        return '0 B'

def _fmt_meta(meta: dict) -> str:
    try:
        parts = []
        for k, v in meta.items():
            parts.append(f'{k}={v}')
        return ', '.join(parts)
    except Exception:
        return ''

@app.command()
def obs_status():
    try:
        status = get_obs_status()
        console.print(f'Status: {status}')
    except Exception as e:
        console.print(f'Error: {e}')

@app.command()
def obs_show():
    try:
        data = get_obs_show()
        table = Table(title='Observations')
        table.add_column('ID', style='cyan')
        table.add_column('Size', style='green')
        table.add_column('Meta', style='yellow')
        for item in data:
            table.add_row(str(item['id']), _fmt_size(item['size']), _fmt_meta(item.get('meta', {})))
        console.print(table)
    except Exception as e:
        console.print(f'Error: {e}')

@app.command()
def obs_level(level: str):
    try:
        result = get_obs_level(level)
        console.print(f'Level {level}: {result}')
    except Exception as e:
        console.print(f'Error: {e}')
if __name__ == '__main__':
    app()
