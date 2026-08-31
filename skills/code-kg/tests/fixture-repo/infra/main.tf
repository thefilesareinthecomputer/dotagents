module "net" {
  source = "./modules/net"
}

output "net_id" {
  value = module.net.vpc_id
}
