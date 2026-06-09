"""CLI entry point for the static website example."""

from typer import Typer
from pulice import PuliceCLI
from static_website.component import StaticWebsite

app = Typer(help='Static website: S3 + CloudFront hosting')
cli = PuliceCLI(app)
cli.register_component(StaticWebsite, name='website')


def main():
    cli()


if __name__ == '__main__':
    main()
