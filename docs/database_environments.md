With ```alembic-environment```, prebuilt database environments are already available to you. The prebuilt ones are ```dev```, ```staging```, and ```prod```. ```dev``` is a locally run postgres container, whereas ```prod``` and ```staging``` are different databases on a Digital Ocean Cluster. Uses ```postgres 18```

### Setting Up ```dev```

To setup your ```dev``` environment. We don't need to pass any kind of environment variables, everything already comes out of the box.

Run the following command to bring up your database:

```uv run python -m environments up dev```

```
PS C:\Users\miles\PycharmProjects\alembic-environment> uv run python 
-m environments up dev
[+] up 2/2
 ✔ Network dev_default              Created                      0.0s
 ✔ Container postgres_dev_container Created                      0.1s
Waiting for dev_db (1/60)...
dev_db ready in 549ms
Running startup steps... [1/2]
Imported 'models' successfully.
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.       
INFO  [alembic.runtime.migration] Will assume transactional DDL.     
Running startup steps... [2/2]
Found 0 seeds for environment 'dev'...
Completed 2 steps successfully.
```

You'll notice the process closes after pinging the database and running ```alembic upgrade head```. No worries! It runs detached, so we don't have to babysit the command line.

Let's go ahead and ping it after to make sure everything's okay:

```
PS C:\Users\miles\PycharmProjects\alembic-environment> uv run python 
-m environments ping dev
dev_db ready in 26ms
```

### Setting Up ```prod``` and ```staging```

First, we'll want to create a Personal Access Token for Digital Ocean. Please visit the following documentation for steps to retrieve it: ```https://docs.digitalocean.com/reference/api/create-personal-access-token/```.

Once you have your token, create and open your env file at ```./.env```:

```
TF_VAR_do_token="{{Your digital ocean token here}}"
```

Once you have listed your token under ```TF_VAR_do_token```, go ahead and terraform your database environments using the following command:

```
uv run --env-file .env python -m environments up prod
```



