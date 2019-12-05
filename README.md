# OSProjectAlpha

https://github.com/Coltux/OSProjectAlpha.git

This project deals with setting up any number of nodes, and a coordinator using Docker-Compose, and then using GRPC and Protocol Buffers in order to handle remote procedure calls between all of them. The objective of this project is to create a system that will implement the GHS algorithm. This is a distributed algorithm that finds the minimum weight spanning tree of a set of nodes. 

## Installation

Firstly, you must run the program network_generator.py and supply the number of nodes so that it can generate the docker-compose.yml file

Then you need to provide a config.ini file for the set of nodes and edges that you want to run it on.

If you wish to change the starting node from node0, then you will have to edit the line in the runCoordinator() method:

```python
wakeUpNode = 0
```
Change the value to the number you wish to wakeup first, or remove the commented section to wakeup a random node. 

Lastly, you must install Docker onto your system. Then, simply use the command:

```bash
docker-compose up --build
```
while in the target directory within your terminal to compile and run the Docker containers that will install everything they need to run within their own containers. 
## Usage

The command:
```bash
docker-compose down
```
can be used to shut down the program from the terminal. Alternatively Ctrl+C can close it out as well, and there is a bug yet to be solved where one of the nodes fails to shutdown properly so this is likely how you will need to exit the program. 

the output of the program is a list of branch edges for each node. This can be used to generate the tree and to determine that the algorithm executed correctly. 

## Collaborators
A file will be found in the project directory that will list all the resources and collaboration used. 
