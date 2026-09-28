Modules referenced by generated projects. Changes here reach projects without running `update`.

Each module follows the standard structure from the [Hashicorp documentation](https://developer.hashicorp.com/terraform/language/modules/develop/structure):

```
.
├── README.md
├── main.tf
├── variables.tf
├── outputs.tf
```

Reference a module from the public repository and pin `?ref=` to a tag:

```terraform
module "cluster" {
  source = "git::https://github.com/Phazebreak-Coatings-Inc/alembic-environment.git//terraform/modules/postgres-cluster?ref=v0.3.1"

  name = var.project_name
}
```
