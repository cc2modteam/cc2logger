from cc2control.servercfgfile import ServerConfigXml, CfgPermissionPeer, CfgModValue


def test_generate_cfg():
    g = ServerConfigXml()
    admin = CfgPermissionPeer()
    admin.is_admin = True
    admin.steam_id = 12345
    g.permissions.append(admin)

    mod1 = CfgModValue()
    mod1.value = "ui-enhancer"
    g.mods.append(mod1)

    print(g.island_count)
    g.island_count = 4

    print(g.island_count)

    output = g.to_xml()
    print(output)

    cfg2 = ServerConfigXml()
    cfg2.from_xml(output)

    assert True