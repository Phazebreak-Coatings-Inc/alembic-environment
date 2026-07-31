With ```alembic-environment```, prebuilt database environments are already available to you. The prebuilt ones are ```dev```, ```staging```, and ```prod```. ```dev``` is a locally run postgres container, whereas ```prod``` and ```staging``` are different databases on a Digital Ocean Cluster.

## Setting Up ```dev```

To setup your ```dev``` environment. We don't need to pass any kind of environment variables, everything already comes out of the box.

Run the following command to bring up your database:

```uv run python -m environments up dev```

```
t> uv run python -m environments up dev
C:\Users\miles\PycharmProjects\alembic-environment\d
atabase
[+] up 2/2
 ✔ Network dev_default              Created     0.1s
 ✔ Container postgres_dev_container Created     0.2s
[alembic-environment] Pinged dev_db in 3174.4ms     
Running startup steps...  [#-]   50%  00:00:03      
[alembic-environment] Modify DevDatabaseSettings.up_
steps to run fns after startup.
Running startup steps...  [##]  100%
PS C:\Users\miles\PycharmProjects\alembic-environmen
t> 
```

You'll notice the process closes after pinging the database. No worries! It runs detached, so we don't have to babysit the command line.

Let's go ahead and ping it after to make sure everything's okay:

```
PS C:\Users\miles\PycharmProjects\alembic-environmen
t> uv run python -m environments ping dev
C:\Users\miles\PycharmProjects\alembic-environment\d
atabase
[alembic-environment] Pinged dev_db in 3139.5ms     
PS C:\Users\miles\PycharmProjects\alembic-environmen
t>
```


### Setting Up ```prod``` and ```staging```

First, we'll want to create a Personal Access Token for Digital Ocean. Please visit the following documentation for steps to retrieve it: ```https://docs.digitalocean.com/reference/api/create-personal-access-token/```.

Once you have your token, create and open your env file at ```./.env```:

```
TF_VAR_do_token="{{Your digital ocean token here}}"
```

Once you have listed your token under ```TF_VAR_do_token```, go ahead and terraform your database environments using the following command:

```
uv run python -m environments up prod
```



