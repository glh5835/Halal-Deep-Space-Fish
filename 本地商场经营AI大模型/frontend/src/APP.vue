<template>
  <el-container style="height: 100vh">
    <el-aside width="200px" style="background:#304156">
      <el-menu router background-color="#304156" text-color="#fff" active-text-color="#ffd04b">
        <el-menu-item index="/dashboard">经营仪表盘</el-menu-item>
        <el-menu-item index="/import">数据导入</el-menu-item>
      </el-menu>
    </el-aside>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>