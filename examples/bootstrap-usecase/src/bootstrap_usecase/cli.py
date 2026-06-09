"""CLI entry point for the bootstrap usecase example."""

from typer import Typer
from bootstrap_usecase.component import BootstrapUsecase
from pulice import PuliceCLI

app = Typer(help='Bootstrap: GitHub repo + AWS CodeBuild self-hosted runners')
cli = PuliceCLI(app)
cli.register_component(BootstrapUsecase, name='bootstrap')


def main():
    cli()


if __name__ == '__main__':
    main()
