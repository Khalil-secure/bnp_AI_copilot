const { FusesPlugin } = require('@electron-forge/plugin-fuses');
const { FuseV1Options, FuseVersion } = require('@electron/fuses');

module.exports = {
    packagerConfig: {
        asar: true,
        name: 'Sales Copilot',
        icon: 'src/assets/logo',
    },
    makers: [
        { name: '@electron-forge/maker-squirrel', config: {} },
        { name: '@electron-forge/maker-zip', platforms: ['darwin'] },
    ],
    plugins: [
        new FusesPlugin({
            version: FuseVersion.V1,
            [FuseV1Options.RunAsNode]: false,
            [FuseV1Options.EnableCookieEncryption]: true,
            [FuseV1Options.EnableNodeOptionsEnvironmentVariable]: false,
            [FuseV1Options.EnableNodeCliInspectArguments]: false,
        }),
    ],
};
