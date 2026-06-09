"""CLI entry point for the Kubernetes namespace example."""

from typer import Typer
from k8s_deploy.component import KubernetesNamespace
from pulice import PuliceCLI

app = Typer(help='Kubernetes: namespace management with resource governance')
cli = PuliceCLI(app)
cli.register_component(KubernetesNamespace, name='namespace')


def main():
    cli()


if __name__ == '__main__':
    main()
