terraform {
  required_version = ">= 1.6"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }

    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "kubernetes" {
  config_path    = "~/.kube/config"
  config_context = "rancher-desktop"
}

provider "helm" {
  kubernetes {
    config_path    = "~/.kube/config"
    config_context = "rancher-desktop"
  }
}
